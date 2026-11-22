# OUT_OF_RANGE

Trong gRPC, **OUT_OF_RANGE là status code số 11**, dùng khi thao tác yêu cầu một vị trí, chỉ số hoặc khoảng dữ liệu nằm ngoài miền hợp lệ hiện tại. Request có thể đúng cấu trúc và các tham số có thể đúng kiểu, nhưng giá trị được yêu cầu vượt quá phạm vi mà tài nguyên hoặc API hiện hỗ trợ. Ví dụ, client yêu cầu đọc một đoạn file bắt đầu sau điểm kết thúc hiện tại.

Trong **SPRING_GRPC**, cần xác định rõ miền hợp lệ của từng operation, quy ước biên của range và hành vi khi dữ liệu thay đổi. OUT_OF_RANGE khác INVALID_ARGUMENT: lỗi đầu thường có thể được khắc phục nếu trạng thái tài nguyên thay đổi, còn lỗi sau thường nằm ở chính giá trị đầu vào. Cũng cần phân biệt request đọc vượt EOF với một stream đang đọc tuần tự và kết thúc tự nhiên ở EOF; trường hợp thứ hai thường hoàn tất bình thường.

## 1. Ý nghĩa của OUT_OF_RANGE

OUT_OF_RANGE có giá trị số **11**. Status phù hợp khi operation được yêu cầu vượt ra ngoài phạm vi hợp lệ của tài nguyên hoặc miền dữ liệu tại thời điểm xử lý.

| Góc nhìn | Ý nghĩa |
| --- | --- |
| Client | Vị trí, chỉ số hoặc khoảng được yêu cầu không nằm trong phạm vi hiện có |
| Server | Operation không thể đáp ứng vì range vượt giới hạn của resource/domain |
| gRPC runtime | Kết thúc RPC với status OUT_OF_RANGE |
| Nghiệp vụ | Client có thể cần đọc lại bounds, chọn range khác hoặc chờ dữ liệu xuất hiện |

Ví dụ:

- Đọc file tại offset vượt quá kích thước file.
- Yêu cầu record sequence lớn hơn sequence mới nhất đã được tạo.
- Truy vấn lịch sử trước mốc dữ liệu retention sớm nhất mà service còn lưu.
- Truy cập phần tử theo index vượt số phần tử của một cấu trúc có miền chỉ số xác định.
- Yêu cầu chunk nằm ngoài tổng số chunk đã công bố.
- Đọc một khoảng thời gian nằm ngoài cửa sổ dữ liệu mà API hỗ trợ.

Status này không tự cho biết giới hạn cụ thể hoặc liệu dữ liệu sẽ xuất hiện sau đó. Nếu client cần điều chỉnh request, server nên cung cấp bounds hoặc cách truy vấn metadata an toàn.

## 2. OUT_OF_RANGE khác INVALID_ARGUMENT

Đây là điểm cốt lõi khi chọn status:

- INVALID_ARGUMENT dùng khi giá trị đầu vào không hợp lệ theo contract, bất kể trạng thái hệ thống.
- OUT_OF_RANGE dùng khi giá trị có ý nghĩa hợp lệ nhưng nằm ngoài phạm vi hiện tại của tài nguyên hoặc dữ liệu.

Ví dụ với RPC đọc file:

| Request | Status/kết quả thường phù hợp | Lý do |
| --- | --- | --- |
| offset âm | INVALID_ARGUMENT | Offset không hợp lệ theo contract |
| length âm | INVALID_ARGUMENT | Độ dài không thể âm |
| offset hợp lệ nhưng vượt file size | OUT_OF_RANGE | Vị trí nằm ngoài dữ liệu hiện có |
| offset trong file, length vượt EOF | OUT_OF_RANGE nếu API yêu cầu range đầy đủ | Khoảng yêu cầu vượt biên |
| offset tại EOF và length bằng 0 | Response rỗng hoặc OK theo contract | Range rỗng có thể hợp lệ |
| offset trong file, không có record phù hợp | OK với kết quả rỗng nếu semantics là query | Không có kết quả không nhất thiết là range error |

Một request có thể thay đổi từ OUT_OF_RANGE thành hợp lệ nếu file được mở rộng hoặc sequence mới được ghi. Ngược lại, lỗi định dạng như offset âm không được khắc phục chỉ bằng cách chờ tài nguyên thay đổi.

## 3. Xác định chính xác biên của range

API phải công bố range dùng quy ước inclusive hay exclusive. Một quy ước phổ biến là khoảng nửa mở:

```text
[start, end)

start được bao gồm
end không được bao gồm
độ dài = end - start
```

Với quy ước này, range [10, 20) chứa các vị trí 10 đến 19 và có độ dài 10. Hai range [10, 20) và [20, 30) liền nhau, không chồng lấn và không bỏ sót phần tử ở biên.

Với API nhận offset và length, cần xác định:

- Offset bắt đầu từ 0 hay 1.
- Length bằng 0 có được chấp nhận không.
- Range vượt EOF bị từ chối toàn bộ hay trả phần dữ liệu còn lại.
- Offset đúng bằng EOF có ý nghĩa gì.
- Có giới hạn length tối đa cho mỗi RPC không.
- Kích thước file/dataset được đọc tại thời điểm nào: lúc bắt đầu call hay trong một snapshot nhất quán.

Không để client và server tự suy luận các quy ước này. Sai khác ở biên thường gây đọc trùng, bỏ sót record hoặc lặp chunk khi phân trang.

## 4. Ví dụ contract Protobuf cho range read

Một RPC đọc chunk có thể được định nghĩa:

```protobuf
syntax = "proto3";

package storage.v1;

service FileService {
  rpc ReadChunk(ReadChunkRequest) returns (ReadChunkReply);
}

message ReadChunkRequest {
  string file_id = 1;
  int64 offset = 2;
  int32 length = 3;
}

message ReadChunkReply {
  bytes data = 1;
  int64 next_offset = 2;
  bool end_of_file = 3;
}
```

Contract nên nói rõ:

- Offset và length tính theo byte hay theo đơn vị khác.
- Offset âm và length âm là INVALID_ARGUMENT.
- Offset nằm ngoài file size là OUT_OF_RANGE.
- Range vượt EOF được từ chối hay cho phép partial read.
- next_offset là vị trí tiếp theo theo cùng quy ước range.
- File có thể thay đổi trong lúc đọc hay request gắn với một snapshot/version.

Nếu API cho phép partial read, response phải thể hiện rõ số byte đã đọc và vị trí tiếp theo. Nếu API cam kết trả đúng toàn bộ range, không được âm thầm trả ít dữ liệu hơn mà client vẫn tưởng request đã hoàn tất.

## 5. Kiểm tra range an toàn trong Java

Khi kiểm tra offset và length, tránh phép cộng có thể overflow. Biểu thức offset + length có thể tràn kiểu long và khiến một range rất lớn bị hiểu nhầm là nhỏ hoặc âm.

Ví dụ kiểm tra:

```java
public void validateReadRange(long offset, int length, long fileSize) {
    if (offset < 0 || length < 0) {
        throw Status.INVALID_ARGUMENT
            .withDescription("Offset và length phải không âm")
            .asRuntimeException();
    }

    if (offset > fileSize || length > fileSize - offset) {
        throw Status.OUT_OF_RANGE
            .withDescription("Range nằm ngoài kích thước file hiện tại")
            .asRuntimeException();
    }
}
```

Điều kiện offset > fileSize được kiểm tra trước phép trừ, nên fileSize - offset không bị âm trong nhánh tiếp theo nếu fileSize đã được xác thực không âm. Nếu API không chấp nhận range rỗng tại EOF, hãy quy định và kiểm tra riêng trường hợp offset == fileSize cùng length == 0.

Không dùng một phép kiểm tra chung cho mọi loại range. Với timestamp, sequence number, page index hoặc byte offset, đơn vị và quy tắc biên có thể khác nhau.

## 6. Mapping domain exception thành OUT_OF_RANGE trong Spring gRPC

Application service nên biểu diễn rõ lỗi domain thay vì để handler suy đoán từ exception Java tổng quát:

```java
public byte[] readChunk(String fileId, long offset, int length) {
    FileMetadata file = fileRepository.findById(fileId)
        .orElseThrow(FileNotFoundException::new);

    rangeValidator.validateReadRange(offset, length, file.size());
    return storage.read(fileId, offset, length);
}
```

Nếu validator phát sinh exception domain, gRPC boundary ánh xạ nó:

```java
try {
    byte[] data = fileService.readChunk(
        request.getFileId(),
        request.getOffset(),
        request.getLength());

    ReadChunkReply reply = ReadChunkReply.newBuilder()
        .setData(ByteString.copyFrom(data))
        .setNextOffset(request.getOffset() + data.length)
        .setEndOfFile(data.length == 0)
        .build();

    observer.onNext(reply);
    observer.onCompleted();
} catch (RangeOutOfBoundsException ex) {
    observer.onError(Status.OUT_OF_RANGE
        .withDescription("Range nằm ngoài dữ liệu hiện có")
        .asRuntimeException());
}
```

Đây là ví dụ minh họa; RangeOutOfBoundsException, repository, storage và response mapping thuộc ứng dụng. Trong code thực tế, cần kiểm tra overflow cả khi tính nextOffset, và xác định chính xác semantics của end_of_file. Với ứng dụng lớn, gom mapping domain exception vào exception mapper/interceptor để giữ hành vi nhất quán giữa các method.

Không nên bắt mọi IndexOutOfBoundsException hoặc IllegalArgumentException rồi trả OUT_OF_RANGE. Những exception đó cũng có thể là bug lập trình hoặc lỗi validation. Chỉ map khi đã xác định lỗi thực sự là request vượt miền dữ liệu mà contract công bố.

## 7. Dữ liệu thay đổi và tính nhất quán của bounds

Một range có thể hợp lệ ở thời điểm client đọc metadata nhưng trở thành ngoài phạm vi trước khi server thực hiện RPC. Ví dụ:

1. Client gọi GetFileMetadata và nhận file size là 1.000 byte.
2. Client chuẩn bị đọc [900, 1.100).
3. File bị truncate xuống 800 byte.
4. Client gọi ReadChunk với range đã tính từ metadata cũ.
5. Server phát hiện range không còn hợp lệ và trả OUT_OF_RANGE.

Nếu file có thể thay đổi, API nên xác định snapshot semantics:

- Đọc theo version/etag đã nhận từ metadata.
- Chấp nhận dữ liệu mới nhất tại thời điểm mỗi call.
- Khóa hoặc snapshot file trong suốt một phiên đọc.
- Trả version hiện tại để client có thể tải metadata mới và quyết định lại.

Với dữ liệu tăng dần như event log, sequence chưa tồn tại có thể xuất hiện sau đó. API có thể trả OUT_OF_RANGE cho truy vấn vượt sequence hiện tại, hoặc cung cấp long-poll/wait semantics riêng. Đừng khiến client polling liên tục nếu API có thể biểu diễn việc chờ dữ liệu mới.

## 8. OUT_OF_RANGE trong pagination và cursor

Pagination có nhiều semantics khác nhau:

- page_size âm hoặc vượt giới hạn được công bố: thường là INVALID_ARGUMENT hoặc được chuẩn hóa theo contract.
- Page token sai định dạng hoặc không thể giải mã: INVALID_ARGUMENT.
- Cursor yêu cầu một sequence nằm ngoài miền dữ liệu còn lưu: có thể là OUT_OF_RANGE.
- Trang hợp lệ nhưng không có phần tử: thường trả OK với danh sách rỗng.
- Cursor hết hạn do snapshot/retention đã bị loại bỏ: status cần được công bố rõ; OUT_OF_RANGE có thể phù hợp nếu cursor chỉ đến vị trí ngoài miền dữ liệu hiện hỗ trợ.

Không nên trả OUT_OF_RANGE cho mọi trang rỗng. Với collection thay đổi, page number vượt số trang hiện tại có thể đơn giản là kết quả rỗng theo contract. Status chỉ nên báo range error khi API định nghĩa rằng caller yêu cầu một vị trí bắt buộc nằm trong miền hợp lệ.

Cursor ổn định thường tốt hơn offset pagination cho dữ liệu thay đổi liên tục. Nếu cursor dựa trên sequence hoặc timestamp, cần định nghĩa retention, tính đơn điệu và hành vi khi dữ liệu cũ bị xóa.

## 9. Khoảng thời gian và miền số

OUT_OF_RANGE cũng có thể dùng cho request truy vấn thời gian hoặc giá trị số nằm ngoài miền dữ liệu được hỗ trợ.

Ví dụ:

- API chỉ lưu dữ liệu telemetry 30 ngày gần nhất; client yêu cầu một mốc cũ hơn retention window.
- Một phép tính yêu cầu sample index lớn hơn số sample hiện có.
- Một báo cáo yêu cầu kỳ dữ liệu chưa được tạo.
- Client yêu cầu timestamp sau giới hạn dữ liệu đã công bố trong snapshot.

Phân biệt:

| Trường hợp | Status/kết quả thường phù hợp |
| --- | --- |
| start time sau end time | INVALID_ARGUMENT |
| Timestamp sai định dạng | INVALID_ARGUMENT |
| Khoảng thời gian hợp lệ nhưng không có event | OK với danh sách rỗng |
| Khoảng yêu cầu nằm ngoài retention window mà API không hỗ trợ | OUT_OF_RANGE |
| Dữ liệu tương lai chưa được tạo nhưng có thể xuất hiện | OUT_OF_RANGE hoặc semantics chờ riêng, theo contract |

Không nên dùng status để thay thế quy tắc nghiệp vụ. Ví dụ “kỳ báo cáo chưa được mở” có thể là FAILED_PRECONDITION, trong khi “sequence yêu cầu vượt sequence tối đa hiện có” có thể là OUT_OF_RANGE.

## 10. Error details và thông tin bounds

Description ngắn thường không đủ để client tự điều chỉnh range. gRPC không định nghĩa một detail chuẩn chuyên biệt cho mọi loại OUT_OF_RANGE; API có thể dùng google.rpc.ErrorInfo với reason ổn định hoặc một Protobuf detail riêng.

Ví dụ thông tin logic:

```text
grpc-status: OUT_OF_RANGE
grpc-message: Range vượt dữ liệu hiện có

ErrorInfo:
  reason: "RANGE_OUT_OF_BOUNDS"
  domain: "storage.example"
  metadata:
    requested_offset: "900"
    requested_length: "200"
    available_size: "1000"
```

Metadata trên chỉ là ví dụ. Trong gRPC Java, richer details có thể được đóng gói trong com.google.rpc.Status và chuyển thành exception bằng io.grpc.protobuf.StatusProto. Không đưa file path nội bộ, tenant khác hoặc thông tin nhạy cảm vào detail. Nếu bounds thay đổi nhanh, hãy ghi rõ đó là snapshot tại thời điểm kiểm tra chứ không phải bảo đảm cho lần gọi sau.

Client nên dựa vào reason hoặc detail type ổn định, không parse câu grpc-message. Nếu API không muốn tiết lộ kích thước hoặc giới hạn thực, chỉ trả status chung và cung cấp method metadata được authorization bảo vệ.

## 11. Client khôi phục sau OUT_OF_RANGE

Khi nhận OUT_OF_RANGE, client cần xác định range hiện tại và quyết định có thể thay đổi request hay phải chờ dữ liệu:

1. Đọc status và structured details nếu có.
2. Tải lại metadata/bounds nếu resource có thể thay đổi.
3. Kiểm tra version/snapshot để biết metadata có còn áp dụng không.
4. Chọn range hợp lệ mới, chia nhỏ request hoặc chờ dữ liệu được tạo.
5. Chỉ gọi lại khi operation vẫn giữ đúng ý nghĩa nghiệp vụ.

Ví dụ blocking stub:

```java
try {
    ReadChunkReply reply = fileStub.readChunk(request);
    consume(reply.getData());
} catch (StatusRuntimeException ex) {
    if (ex.getStatus().getCode() == Status.Code.OUT_OF_RANGE) {
        // Tải lại file metadata, kiểm tra version và chọn range mới.
    } else {
        // Xử lý status khác.
    }
}
```

Không tự động clamp mọi range về giới hạn hiện tại. Nếu client yêu cầu [900, 1100) nhưng server âm thầm trả [900, 1000), client có thể hiểu nhầm rằng đã nhận đủ 200 byte. Chỉ trả partial result nếu contract nói rõ cách biểu diễn số byte thực nhận và vị trí tiếp theo.

## 12. OUT_OF_RANGE và streaming RPC

Cần phân biệt hai trường hợp:

- Request range vượt giới hạn ngay từ đầu: server có thể từ chối RPC bằng OUT_OF_RANGE trước khi phát message.
- Stream đọc tuần tự đến EOF tự nhiên: đây thường là kết thúc bình thường; server gọi onCompleted() và client nhận status OK.

Ví dụ, ReadFile(offset, length) yêu cầu chính xác 500 byte nhưng chỉ còn 200 byte trong file. Nếu contract yêu cầu đủ 500 byte, server có thể trả OUT_OF_RANGE. Ngược lại, StreamFileFrom(offset) có thể phát mọi byte còn lại rồi kết thúc OK khi đến EOF.

Với server streaming, nếu file bị truncate trong lúc stream, contract phải quy định snapshot, partial result hoặc kết thúc bằng status lỗi. Client cần biết các message đã nhận có được xem là dữ liệu hợp lệ hay cần khởi động lại từ checkpoint.

Với bidirectional streaming, mỗi message có thể yêu cầu một range riêng. Nếu một message vượt biên, API phải xác định lỗi đó kết thúc toàn stream hay chỉ được trả như một kết quả cho item đó.

## 13. Kiểm thử OUT_OF_RANGE

Test cần tập trung vào biên, thay đổi state và semantics stream:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Offset âm hoặc length âm | INVALID_ARGUMENT |
| Offset lớn hơn file size | OUT_OF_RANGE |
| Range vượt EOF | Hành vi strict/partial đúng contract |
| Offset đúng EOF, length bằng 0 | Kết quả theo quy ước range rỗng |
| Offset đúng EOF, length dương | OUT_OF_RANGE nếu strict read |
| Phép cộng offset + length có thể overflow | Không lọt qua validation |
| File truncate sau khi client đọc metadata | Version/bounds được kiểm tra và status đúng |
| Query range hợp lệ nhưng không có record | OK với kết quả rỗng nếu semantics là query |
| Cursor/token malformed | INVALID_ARGUMENT |
| Cursor nằm ngoài retention window | Status theo contract, có thể OUT_OF_RANGE |
| Stream chạm EOF tự nhiên | Hoàn tất OK, không báo range error |
| Stream bị truncate giữa chừng | Hành vi partial/checkpoint đúng contract |

Unit test kiểm tra validator và boundary arithmetic. Integration test qua gRPC client/server xác nhận status thực tế và rich details. Với file/object storage hoặc database, test cần mô phỏng thay đổi kích thước/version giữa lúc đọc metadata và lúc gọi range read.

## 14. Observability và vận hành

OUT_OF_RANGE tăng có thể cho thấy client dùng metadata cũ, cursor không ổn định, retention policy thay đổi hoặc contract về bounds chưa rõ.

Nên theo dõi:

- Số lượng/tỷ lệ OUT_OF_RANGE theo service/method.
- Loại range: byte offset, sequence, page cursor, timestamp hoặc numeric index.
- Nhóm nguyên nhân đã chuẩn hóa: negative input, past end, expired retention, stale snapshot.
- Client/SDK version và resource version nếu được phép.
- Tỷ lệ request thành công sau khi client tải lại metadata.
- Tỷ lệ partial read, EOF và stream restart.
- Trace/correlation ID để nối request với lần đọc metadata trước đó.

Không đưa file ID, tenant ID, user ID hoặc cursor đầy đủ vào metric label có cardinality cao. Log có thể ghi range và bounds đã được phép, nhưng cần tránh lộ path nội bộ hoặc dữ liệu riêng tư. Nếu bounds có thể nhạy cảm, ghi reason code và trace ID thay vì giá trị cụ thể.

## 15. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Dùng INVALID_ARGUMENT cho mọi range vượt biên | Client không biết state thay đổi có thể làm request hợp lệ | Phân biệt giá trị sai với range ngoài miền hiện tại |
| Trả OUT_OF_RANGE cho query rỗng | Biến kết quả hợp lệ thành lỗi | Trả OK với collection rỗng khi đúng semantics |
| Không định nghĩa inclusive/exclusive bounds | Đọc trùng hoặc bỏ sót dữ liệu ở biên | Công bố quy ước range và đơn vị |
| Tính offset + length mà không chống overflow | Range lớn có thể vượt qua validation | Dùng phép so sánh an toàn trước phép cộng |
| Âm thầm cắt ngắn range | Client tưởng đã nhận đủ dữ liệu | Strict error hoặc partial response được mô tả rõ |
| Coi EOF tự nhiên là OUT_OF_RANGE | Stream bình thường bị báo lỗi | Hoàn tất OK khi stream đạt EOF theo contract |
| Dùng metadata bounds cũ mà không kiểm tra version | Đọc dữ liệu sai sau truncate/update | Snapshot/version hoặc kiểm tra bounds tại server |
| Retry cùng range không thay đổi | Lặp lỗi và tăng tải | Tải lại bounds, chọn range mới hoặc chờ state đổi |

## 16. Checklist thiết kế OUT_OF_RANGE

Trước khi công bố gRPC method, hãy xác định:

1. **Miền hợp lệ là gì?** Byte offset, index, sequence, timestamp hay page cursor.
2. **Quy ước biên ra sao?** Inclusive/exclusive, zero-based, length bằng 0.
3. **Giá trị nào là INVALID_ARGUMENT?** Số âm, sai định dạng hoặc cấu trúc không hợp lệ.
4. **Khi nào là OUT_OF_RANGE?** Vượt bounds hiện tại hoặc ngoài retention window.
5. **Dữ liệu có thể thay đổi không?** Snapshot/version và thời điểm kiểm tra bounds.
6. **Strict hay partial read?** Response phải biểu diễn số lượng thực nhận và checkpoint.
7. **Có chống overflow không?** Kiểm tra phép tính range trước khi truy cập resource.
8. **Client khôi phục thế nào?** Đọc metadata mới, chọn range khác hoặc chờ dữ liệu.
9. **Streaming EOF có semantics gì?** Phân biệt kết thúc tự nhiên với request range sai.
10. **Telemetry có chẩn đoán được nguyên nhân mà không lộ dữ liệu không?**

## 17. Ghi nhớ

OUT_OF_RANGE là gRPC status code 11, dùng khi vị trí, chỉ số hoặc khoảng dữ liệu được yêu cầu nằm ngoài miền hợp lệ hiện tại. Nó khác INVALID_ARGUMENT, vốn biểu thị giá trị đầu vào sai theo contract. Một query hợp lệ không có kết quả thường vẫn trả OK với collection rỗng; stream đọc tuần tự đến EOF tự nhiên cũng thường hoàn tất OK.

Trong Spring gRPC, hãy công bố rõ range bounds, đơn vị, quy ước inclusive/exclusive và strict/partial semantics. Validate đầu vào và chống overflow trước khi truy cập dữ liệu; map domain range exception thành Status.OUT_OF_RANGE. Nếu bounds có thể thay đổi, dùng snapshot/version hoặc cho client tải lại metadata. Rich error details có thể mô tả reason và bounds an toàn. Client cần điều chỉnh range thay vì retry nguyên request, còn streaming phải phân biệt range request sai với EOF bình thường. Thiết kế rõ ràng giúp API tránh đọc thiếu/trùng dữ liệu và hỗ trợ client phục hồi đúng cách.

### Tài liệu tham khảo

- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC – Error handling](https://grpc.io/docs/guides/error/)
- [Google API – Error model](https://cloud.google.com/apis/design/errors)
- [Google API – Resource-oriented design](https://cloud.google.com/apis/design/resources)
- [Java – Math.addExact](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
