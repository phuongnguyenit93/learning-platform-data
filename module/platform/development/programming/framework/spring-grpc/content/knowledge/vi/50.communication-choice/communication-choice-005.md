# Chọn client streaming cho upload hoặc batch

Client streaming phù hợp khi một client cần gửi **nhiều message trong cùng một RPC** và server chỉ cần trả về **một kết quả tổng hợp** sau khi nhận hết dữ liệu. Mô hình này thường dùng cho upload tệp theo từng phần, nhập dữ liệu hàng loạt hoặc gửi một chuỗi bản ghi lớn mà không muốn gom toàn bộ vào một request unary.

Điểm quyết định không chỉ là dữ liệu lớn hay nhỏ. Hãy chọn client streaming khi dữ liệu được tạo hoặc đọc tuần tự ở phía client, server có thể xử lý dần từng message, và nghiệp vụ có thể chốt kết quả ở cuối luồng. Nếu client cần nhận phản hồi cho từng phần ngay trong lúc gửi, cần cân nhắc bidirectional streaming.

## 1. Hiểu đúng mô hình client streaming

Trong một client-streaming RPC, client gửi một chuỗi request message rồi đóng nửa gửi bằng cách hoàn tất stream. Server nhận các message qua callback, xử lý chúng và gửi về đúng một response cuối cùng.

Trình tự cơ bản:

1. Client mở RPC.
2. Client gửi message đầu tiên để khai báo thông tin upload hoặc batch.
3. Client gửi lần lượt các chunk hoặc record.
4. Client gọi **onCompleted()** để báo đã gửi hết request.
5. Server kiểm tra dữ liệu cuối luồng, hoàn tất nghiệp vụ và trả một response.
6. Client nhận response rồi nhận callback hoàn tất.

Việc client gọi **onCompleted()** chỉ có nghĩa là phía client đã kết thúc gửi request. Nó không khẳng định server đã lưu thành công dữ liệu. Client chỉ nên xác nhận upload thành công sau khi nhận response thành công từ server.

| Kiểu RPC | Dữ liệu client gửi | Dữ liệu server trả | Trường hợp phù hợp |
|---|---|---|---|
| Unary | Một request | Một response | Một lệnh hoặc một payload nhỏ, có giới hạn rõ |
| Server streaming | Một request | Nhiều response | Client gửi tiêu chí truy vấn, server trả nhiều kết quả |
| Client streaming | Nhiều request | Một response | Upload, import, batch cần một kết quả tổng hợp |
| Bidirectional streaming | Nhiều request | Nhiều response | Hai phía cần trao đổi liên tục, phản hồi từng phần hoặc điều khiển luồng |

Ví dụ, một ứng dụng gửi tệp 500 MB có thể chia tệp thành nhiều chunk và gửi qua một client-streaming RPC. Server ghi từng chunk vào vùng lưu tạm, kiểm tra checksum sau khi nhận hết, rồi trả về mã upload và vị trí lưu. Tệp không cần được ghép thành một mảng byte lớn trong bộ nhớ của client hoặc server.

## 2. Khi nào nên chọn client streaming?

Chọn client streaming khi phần lớn các điều kiện sau đúng:

- Dữ liệu gồm nhiều phần có thể gửi tuần tự: chunk của tệp, bản ghi import, sự kiện hoặc mục trong một batch.
- Client có thể tiếp tục đọc dữ liệu trong khi RPC đang mở, thay vì phải tạo toàn bộ payload trước.
- Server có thể xử lý hoặc lưu từng phần khi chúng đến.
- Kết quả nghiệp vụ có thể trả một lần ở cuối, ví dụ số byte đã lưu, checksum, số bản ghi thành công và số bản ghi bị từ chối.
- Một RPC có thể đại diện cho một đơn vị công việc đủ rõ để áp dụng deadline, xác thực, quota và theo dõi trạng thái.

Không nên chọn client streaming chỉ vì muốn “gửi nhiều dữ liệu”. Hãy cân nhắc các kiểu khác trong những trường hợp sau:

- Dùng unary nếu request nhỏ, có giới hạn kích thước chắc chắn, cần xử lý nguyên tử và một request/response giúp hợp đồng đơn giản hơn.
- Dùng server streaming nếu client chỉ gửi một yêu cầu nhưng cần nhận danh sách hoặc kết quả dài từ server.
- Dùng bidirectional streaming nếu client cần nhận xác nhận, tiến độ hoặc kết quả riêng cho từng chunk/record trong khi vẫn tiếp tục gửi.
- Dùng một giao thức upload có thể tiếp tục sau khi mất kết nối nếu phiên upload phải sống qua nhiều RPC hoặc qua nhiều lần client khởi động lại. Client streaming đơn lẻ không tự cung cấp khả năng resume.

Một câu hỏi hữu ích khi chọn kiểu RPC là: **server có cần trả lời trước khi client gửi xong không?** Nếu không, client streaming thường là lựa chọn tự nhiên. Nếu có, hãy xác định có cần bidirectional streaming hay có thể tách tiến độ thành một RPC truy vấn trạng thái khác.

## 3. Thiết kế hợp đồng Protocol Buffers

Với upload, nên tách thông tin mô tả tệp khỏi dữ liệu chunk. Message đầu tiên khai báo phiên upload; các message tiếp theo mang dữ liệu. Dùng **oneof** để thể hiện rõ loại nội dung của mỗi message.

Ví dụ hợp đồng:

~~~proto
syntax = "proto3";

package files.v1;

option java_multiple_files = true;
option java_package = "com.example.files.v1";

service FileService {
  rpc Upload(stream UploadRequest) returns (UploadResponse);
}

message UploadRequest {
  oneof payload {
    UploadStart start = 1;
    UploadChunk chunk = 2;
  }
}

message UploadStart {
  string upload_id = 1;
  string file_name = 2;
  string content_type = 3;
  int64 expected_size_bytes = 4;
  bytes expected_sha256 = 5;
}

message UploadChunk {
  uint64 sequence = 1;
  bytes data = 2;
}

message UploadResponse {
  string upload_id = 1;
  int64 stored_size_bytes = 2;
  bytes sha256 = 3;
  string object_reference = 4;
}
~~~

Hợp đồng này thể hiện một quy tắc quan trọng: message đầu tiên phải là **start**, sau đó mới đến các **chunk**. Server cần từ chối stream nếu chunk xuất hiện trước phần khai báo, có nhiều phần khai báo không hợp lệ, hoặc sequence không đúng quy tắc đã thống nhất.

Các trường có mục đích riêng:

- **upload_id** nhận diện một phiên upload và hỗ trợ đối chiếu khi client cần kiểm tra trạng thái.
- **expected_size_bytes** cho phép server kiểm tra kích thước dự kiến và áp dụng quota sớm.
- **expected_sha256** cho phép xác minh nội dung sau khi nhận đủ dữ liệu.
- **sequence** giúp phát hiện chunk thiếu, trùng hoặc sai thứ tự.
- **object_reference** là tham chiếu tới tài nguyên đã lưu; tránh trả đường dẫn nội bộ của máy chủ nếu không cần thiết.

Không bắt buộc mọi upload đều cần **upload_id**, checksum và sequence. Hãy giữ những trường giúp bảo đảm tính toàn vẹn hoặc phục vụ nghiệp vụ. Với một stream đơn giản qua một kết nối, thứ tự message vốn được giữ trong RPC; sequence hữu ích khi cần kiểm tra dữ liệu ở tầng ứng dụng, ghi nhận tiến độ hoặc hỗ trợ resume qua nhiều RPC.

### Thiết kế cho batch

Với import dữ liệu, có thể dùng cùng nguyên tắc: message đầu tiên khai báo batch, các message sau mang record. Ví dụ rút gọn:

~~~proto
service ImportService {
  rpc Import(stream ImportRequest) returns (ImportSummary);
}

message ImportRequest {
  oneof payload {
    ImportStart start = 1;
    ImportRecord record = 2;
  }
}

message ImportStart {
  string batch_id = 1;
  string idempotency_key = 2;
}

message ImportRecord {
  uint64 sequence = 1;
  string external_id = 2;
  bytes payload = 3;
}

message ImportSummary {
  string batch_id = 1;
  int64 accepted = 2;
  int64 rejected = 3;
  repeated RecordError sample_errors = 4;
}

message RecordError {
  uint64 sequence = 1;
  string code = 2;
  string message = 3;
}
~~~

Nếu record có cấu trúc ổn định, hãy mô tả bằng message Protocol Buffers cụ thể thay cho **bytes payload**. Chỉ dùng payload opaque khi định dạng được quản lý ở một tầng khác hoặc cần hỗ trợ nhiều schema.

Response cuối nên chứa số lượng tổng hợp và một lượng lỗi mẫu có giới hạn. Không nên nhồi hàng triệu lỗi vào response cuối; response cũng là một gRPC message và chịu giới hạn kích thước. Với báo cáo lỗi lớn, lưu báo cáo thành tài nguyên riêng rồi trả về tham chiếu để client tải sau.

## 4. Quy ước giao thức của stream

Trước khi triển khai, hãy ghi rõ các quy tắc mà client và server cùng phải tuân thủ:

- Message đầu tiên là message khởi tạo (**start**).
- Chỉ nhận chunk hoặc record sau khi khởi tạo thành công.
- Sequence bắt đầu từ giá trị đã quy định, thường là 0 hoặc 1, và tăng theo từng message.
- Quy định rõ chunk rỗng có hợp lệ hay không. Thông thường không cần gửi chunk rỗng.
- Quy định tổng kích thước tối đa, kích thước mỗi chunk, số record tối đa và thời gian tối đa của một stream.
- Khi client gọi **onCompleted()**, server xác minh số byte, số record, checksum và điều kiện nghiệp vụ trước khi commit.
- Khi client hủy hoặc gửi lỗi, server dọn dữ liệu tạm hoặc giữ checkpoint theo chính sách resume đã thiết kế.
- Server chỉ trả một response cuối cùng khi RPC còn hoạt động và quá trình xử lý hoàn tất.

Đừng dùng **onCompleted()** như một message kết thúc do ứng dụng tự định nghĩa. Đây là tín hiệu half-close của gRPC. Nếu nghiệp vụ cần trailer chứa tổng số record hoặc checksum do client khai báo, hãy đưa thông tin đó vào phần **start** hoặc một message cuối được mô tả rõ trong schema; sau đó vẫn gọi **onCompleted()** để kết thúc luồng gửi.

Với batch, cần quyết định trước khi xử lý rằng batch có tính chất **all-or-nothing** hay **partial success**. All-or-nothing nghĩa là chỉ công bố kết quả khi toàn bộ batch hợp lệ. Partial success nghĩa là từng record có thể được chấp nhận hoặc từ chối độc lập, và response cuối tổng hợp hai nhóm. Client phải hiểu rõ chính sách này để không diễn giải một response thành công là mọi record đều thành công.

## 5. Gửi stream từ Java client

Với generated async stub, phương thức client-streaming nhận một **StreamObserver** để nhận response cuối và trả về một **StreamObserver** để client gửi request message.

Ví dụ sau minh họa việc đọc tệp theo chunk 64 KiB:

~~~java
StreamObserver<UploadRequest> requestObserver =
        asyncStub.withDeadlineAfter(5, TimeUnit.MINUTES)
                .upload(new StreamObserver<UploadResponse>() {
                    @Override
                    public void onNext(UploadResponse response) {
                        // Chỉ xác nhận upload sau khi nhận response này.
                        System.out.println("Stored: " + response.getObjectReference());
                    }

                    @Override
                    public void onError(Throwable error) {
                        // Ghi nhận lỗi RPC và cập nhật trạng thái upload.
                    }

                    @Override
                    public void onCompleted() {
                        // Server đã kết thúc response stream.
                    }
                });

try (InputStream input = Files.newInputStream(filePath)) {
    UploadStart start = UploadStart.newBuilder()
            .setUploadId(uploadId)
            .setFileName(filePath.getFileName().toString())
            .setContentType(contentType)
            .setExpectedSizeBytes(Files.size(filePath))
            .build();

    requestObserver.onNext(
            UploadRequest.newBuilder().setStart(start).build());

    byte[] buffer = new byte[64 * 1024];
    long sequence = 0;
    int count;

    while ((count = input.read(buffer)) != -1) {
        UploadChunk chunk = UploadChunk.newBuilder()
                .setSequence(sequence++)
                .setData(ByteString.copyFrom(buffer, 0, count))
                .build();

        requestObserver.onNext(
                UploadRequest.newBuilder().setChunk(chunk).build());
    }

    requestObserver.onCompleted();
} catch (IOException | RuntimeException error) {
    requestObserver.onError(error);
    throw error;
}
~~~

Đây là ví dụ tối giản để làm rõ API. Trong ứng dụng thực tế, cần xử lý response bất đồng bộ bằng callback, future hoặc cơ chế điều phối phù hợp; không chặn event loop hay thread xử lý request web chỉ để chờ stream hoàn tất. Cũng cần bảo đảm chỉ một luồng điều khiển gọi **onNext**, **onCompleted** hoặc **onError** trên cùng request observer, trừ khi đã đồng bộ hóa đúng cách.

**withDeadlineAfter(...)** đặt deadline cho toàn bộ RPC. Hãy chọn thời gian dựa trên kích thước dữ liệu, băng thông dự kiến, tốc độ lưu trữ và thời gian xử lý phía server. Deadline quá ngắn khiến upload hợp lệ bị hủy giữa chừng; deadline quá dài khiến tài nguyên có thể bị giữ lâu khi client gặp sự cố.

### Không gửi nhanh hơn khả năng truyền

Vòng lặp trên đọc và gửi liên tục. Với tệp nhỏ hoặc tải thử nghiệm, cách này dễ hiểu. Với tệp lớn hoặc mạng chậm, producer có thể tạo message nhanh hơn khả năng gửi của transport; dữ liệu chờ trong hàng đợi sẽ làm tăng bộ nhớ sử dụng.

Trong grpc-java, có thể dùng **ClientResponseObserver** để nhận **ClientCallStreamObserver** trong **beforeStart(...)**. Theo dõi **isReady()** và đăng ký **setOnReadyHandler(...)** để chỉ đọc và gửi chunk tiếp theo khi stream sẵn sàng. Hãy giữ số chunk đang chờ ở mức giới hạn và tuần tự hóa việc đọc/gửi. Callback sẵn sàng có thể được gọi nhiều lần; producer cần tránh chạy đồng thời hai vòng gửi.

Một cách tổ chức hiệu quả là tách nguồn dữ liệu thành producer có giới hạn và một bộ gửi duy nhất. Bộ gửi chỉ lấy thêm chunk khi gRPC báo sẵn sàng. Nhờ đó, tốc độ đọc từ đĩa được điều tiết theo khả năng truyền của RPC.

## 6. Nhận và xử lý stream ở server

Generated service base class cung cấp phương thức nhận **StreamObserver<UploadRequest>** và trả về một observer để server nhận request message. Server có thể xử lý từng message trong callback **onNext**, rồi chỉ gửi **UploadResponse** sau callback **onCompleted**.

Luồng xử lý nên có các bước sau:

1. Khi nhận message đầu tiên, xác thực quyền upload, **upload_id**, tên tệp, loại nội dung, quota và kích thước dự kiến.
2. Tạo vùng lưu tạm hoặc phiên upload. Chưa công bố tệp như một tài nguyên hoàn chỉnh.
3. Với mỗi chunk, kiểm tra đúng loại message, sequence, kích thước chunk và tổng byte. Ghi chunk vào vùng lưu tạm và cập nhật checksum.
4. Khi nhận **onCompleted()**, kiểm tra tổng kích thước và checksum thực tế, sau đó commit hoặc publish tài nguyên.
5. Trả đúng một response chứa kết quả cuối và gọi **onCompleted()** trên response observer.
6. Nếu nhận **onError()** hoặc RPC bị hủy, đóng file, giải phóng tài nguyên và xóa dữ liệu tạm hoặc lưu checkpoint theo chính sách đã chọn.

Phần cốt lõi có thể tách thành một dịch vụ nghiệp vụ như **UploadSession**, chịu trách nhiệm **start**, **writeChunk**, **commit** và **abort**. gRPC service chỉ điều phối callback và ánh xạ lỗi nghiệp vụ thành gRPC status. Cách này giúp kiểm thử logic lưu tệp độc lập với transport.

Không nên giữ toàn bộ nội dung upload trong một **ByteArrayOutputStream** nếu kích thước có thể lớn. Hãy ghi theo luồng tới file tạm, object storage hoặc một sink có giới hạn bộ nhớ. Nếu ghi đĩa chậm, tránh chặn thread callback gRPC lâu; dùng executor có giới hạn và điều tiết inbound flow control để server không nhận thêm message vượt khả năng xử lý.

Trong grpc-java, khi cần điều khiển lượng request message server nhận trước, có thể dùng manual inbound flow control thông qua **ServerCallStreamObserver**: tắt chế độ tự động request và chỉ request thêm message sau khi đã xử lý xong phần trước. Chỉ nên bật cơ chế này khi đã hiểu rõ vòng đời callback và cách phối hợp executor; nếu không, có thể làm stream bị treo do quên request thêm message.

## 7. Deadline, cancellation và trạng thái lỗi

Client streaming là một RPC kéo dài trong suốt thời gian gửi dữ liệu. Cần xem deadline, cancellation và cleanup là một phần của hợp đồng vận hành.

Một số status thường phù hợp:

| Status | Khi nào dùng |
|---|---|
| **INVALID_ARGUMENT** | Message sai cấu trúc, thiếu start, sequence sai hoặc checksum không khớp |
| **UNAUTHENTICATED** | Client chưa cung cấp thông tin xác thực hợp lệ |
| **PERMISSION_DENIED** | Client đã xác thực nhưng không có quyền upload hoặc import |
| **RESOURCE_EXHAUSTED** | Vượt quota, kích thước, số lượng hoặc giới hạn tài nguyên |
| **DEADLINE_EXCEEDED** | RPC vượt thời hạn đã đặt |
| **CANCELLED** | Client hoặc bên gọi chủ động hủy RPC |
| **UNAVAILABLE** | Thành phần phụ thuộc tạm thời không thể phục vụ |
| **INTERNAL** | Lỗi bất ngờ phía server, không nên tiết lộ chi tiết nội bộ |

Khi client hủy hoặc deadline hết hạn, server cần dừng xử lý càng sớm càng tốt và giải phóng tài nguyên. Kiểm tra trạng thái cancellation trước các công việc tốn kém, đặc biệt khi đang ghi dữ liệu hoặc gọi dịch vụ lưu trữ. Nếu dữ liệu tạm có thể còn lại sau khi process bị dừng đột ngột, cần có cơ chế dọn dẹp theo TTL.

Không trả status **OK** chỉ vì server đã nhận đủ message. Hãy chỉ trả thành công sau khi checksum, quota, validation và thao tác commit cần thiết đã hoàn tất. Nếu ghi dữ liệu thành công nhưng bước publish thất bại, response phải phản ánh đúng trạng thái thực tế để client không hiểu nhầm.

## 8. Retry, idempotency và khả năng tiếp tục upload

Một client-streaming RPC không tự biến thành giao thức upload có thể tiếp tục. Khi kết nối mất giữa chừng, client có thể không biết server đã ghi nhận đến chunk nào. Việc gửi lại toàn bộ stream có thể tốn băng thông hoặc tạo dữ liệu trùng nếu server đã commit nhưng response bị mất.

Thiết kế một trong các chính sách sau:

- **Upload một lần:** nếu RPC lỗi, hủy phiên tạm và client bắt đầu lại từ đầu. Dùng khi tệp nhỏ hoặc chi phí gửi lại chấp nhận được.
- **Upload có idempotency:** client gửi **upload_id** hoặc idempotency key ổn định. Server nhận diện yêu cầu lặp và không tạo tài nguyên trùng.
- **Upload có resume:** server lưu checkpoint theo **upload_id**, trả trạng thái đã nhận đến byte hoặc sequence nào qua một RPC truy vấn riêng. Client mở RPC mới và gửi tiếp từ vị trí được xác nhận.
- **Batch có deduplication:** dùng **batch_id** và định danh record ổn định để server nhận diện record đã xử lý khi client phải gửi lại.

Không nên giả định retry tự động của gRPC sẽ phát lại an toàn một stream đã gửi một phần. Khả năng retry còn phụ thuộc chính sách retry, thời điểm RPC được commit và dữ liệu request còn được buffer hay không. Với upload lớn, hãy thiết kế idempotency và resume ở tầng ứng dụng nếu nghiệp vụ yêu cầu.

Với batch, hãy xác định ranh giới transaction. Nếu một record lỗi, server dừng cả batch hay tiếp tục xử lý các record còn lại? Nếu partial success được chấp nhận, cần định nghĩa rõ record nào đã commit và cách client truy vấn hoặc gửi lại phần thất bại. Không nên dựa vào việc client đoán trạng thái sau một lỗi mạng.

## 9. Kích thước chunk, giới hạn và hiệu năng

Client streaming giúp tránh tạo một request khổng lồ, nhưng mỗi message vẫn có giới hạn kích thước. Giới hạn inbound/outbound của gRPC, cấu hình channel/server, proxy và gateway đều có thể ảnh hưởng. Hãy cấu hình và kiểm thử giới hạn ở tất cả các chặng thay vì cho rằng stream cho phép gửi message không giới hạn.

Các nguyên tắc thực tế:

- Bắt đầu thử nghiệm với chunk có kích thước vừa phải, chẳng hạn 64–256 KiB, rồi benchmark trên hạ tầng thực tế để tìm điểm cân bằng giữa overhead và bộ nhớ.
- Đặt giới hạn kích thước cho từng chunk và tổng kích thước của một upload.
- Không gom toàn bộ file vào một message protobuf. HTTP/2 chia frame ở tầng truyền tải không làm mất giới hạn kích thước message gRPC.
- Với batch có nhiều record nhỏ, cân nhắc gộp một số record vào một message bounded để giảm overhead, nhưng vẫn giữ giới hạn kích thước và khả năng xử lý từng record.
- Chỉ bật compression khi dữ liệu có thể nén đáng kể. Dữ liệu đã nén như ZIP, JPEG hoặc video thường không tiết kiệm được nhiều nhưng vẫn tiêu tốn CPU.
- Đo throughput, độ trễ, bộ nhớ, CPU, số chunk và thời gian xử lý ở server; benchmark với kích thước tệp và mức đồng thời gần với tải thật.

Một stream có thể giữ kết nối và tài nguyên server trong thời gian dài. Vì vậy, cần giới hạn số upload đồng thời theo client hoặc tenant, tổng dung lượng đang nhận, tốc độ gửi và thời gian không có tiến triển. Flow control giúp điều tiết lượng dữ liệu đang truyền; quota và deadline bảo vệ hệ thống khỏi các phiên chiếm tài nguyên quá lâu.

## 10. Bảo mật và kiểm soát quyền truy cập

Upload và import thường mang dữ liệu nhạy cảm. Cần áp dụng TLS hoặc mTLS theo mô hình triển khai, xác thực client và kiểm tra quyền trên từng tài nguyên hoặc tenant. Metadata có thể mang token hoặc thông tin nhận diện nhưng không nên chứa nội dung file hoặc payload lớn.

Ở phía server:

- Xác thực và kiểm tra quyền trước khi cấp tài nguyên lưu tạm.
- Chuẩn hóa tên file; không dùng trực tiếp tên do client gửi để tạo đường dẫn trên filesystem.
- Kiểm tra content type và định dạng thực tế nếu nghiệp vụ yêu cầu.
- Giới hạn kích thước, số chunk, số record, số stream đồng thời và quota theo tenant.
- Tránh ghi payload, token hoặc dữ liệu cá nhân vào log.
- Đảm bảo dữ liệu chưa hoàn tất không được truy cập như một tài nguyên đã publish.

Nếu client có thể gửi dữ liệu từ nguồn không tin cậy, hãy kiểm tra malware hoặc nội dung độc hại theo quy trình của hệ thống trước khi đưa file vào luồng sử dụng chính thức.

## 11. Tích hợp trong ứng dụng Spring gRPC

Protocol Buffers định nghĩa hợp đồng và plugin sinh mã Java tạo service base class, stub và các kiểu message. Phía server triển khai phương thức client-streaming được sinh từ hợp đồng; phía client dùng async stub để gửi chuỗi message.

Trong ứng dụng Spring, hãy đăng ký triển khai gRPC service và cấu hình channel/client stub theo starter hoặc phiên bản Spring gRPC đang dùng. Đảm bảo client interceptor, deadline mặc định, TLS, authentication và tracing được gắn vào đúng channel. Việc một interceptor tồn tại dưới dạng Spring bean không tự bảo đảm mọi channel đều sử dụng nó; cần xác minh cơ chế đăng ký của starter trong dự án.

Nên đặt xử lý file hoặc batch trong service nghiệp vụ Spring riêng. Lớp gRPC adapter tập trung vào việc nhận stream, kiểm tra giao thức và chuyển dữ liệu đến service. Service nghiệp vụ quản lý phiên upload, storage, transaction và idempotency. Cấu trúc này giúp cùng một logic có thể được kiểm thử mà không cần khởi động gRPC server.

Không giữ một transaction cơ sở dữ liệu mở trong toàn bộ thời gian client gửi một file lớn. Một stream có thể kéo dài nhiều phút và làm giữ connection hoặc lock. Thay vào đó, lưu dữ liệu tạm theo từng phần, sau đó thực hiện transaction ngắn ở bước commit cuối. Với batch, chọn transaction theo lô hoặc theo record dựa trên yêu cầu nhất quán và khả năng rollback.

## 12. Kiểm thử client streaming

Kiểm thử cần bao phủ hợp đồng stream, tính toàn vẹn dữ liệu, lỗi và tải:

1. Gửi một upload hợp lệ gồm start và nhiều chunk; xác nhận response cuối có đúng kích thước và checksum.
2. Gửi stream không có start hoặc gửi chunk trước start; xác nhận server trả **INVALID_ARGUMENT**.
3. Gửi sequence bị thiếu, trùng hoặc sai thứ tự; xác nhận chính sách xử lý được thực thi.
4. Gửi file rỗng, file đúng giới hạn và file vượt giới hạn.
5. Ngắt kết nối hoặc hủy RPC giữa chừng; xác nhận dữ liệu tạm được dọn hoặc checkpoint được lưu đúng.
6. Làm checksum sai; xác nhận server không publish dữ liệu không hợp lệ.
7. Gửi lại cùng idempotency key; xác nhận không tạo tài nguyên trùng.
8. Làm chậm phía server hoặc client để kiểm tra flow control và mức sử dụng bộ nhớ.
9. Kiểm thử deadline, authentication, quota và nhiều upload đồng thời.
10. Với batch, kiểm thử cả all-or-nothing lẫn partial success theo đúng chính sách đã công bố.

In-process gRPC server/channel hữu ích để kiểm thử interceptor, thứ tự message và status. Tuy nhiên, kiểm thử in-process không bao phủ TLS, proxy, gateway, HTTP/2 và giới hạn kích thước trên mạng. Nên có thêm kiểm thử tích hợp qua cấu hình triển khai gần với production cho các vấn đề liên quan transport.

## 13. Quan sát vận hành

Theo dõi mỗi RPC bằng các chỉ số tổng hợp:

- Số stream bắt đầu, hoàn tất, bị hủy và thất bại theo status.
- Số byte, số chunk hoặc record đã nhận.
- Thời gian nhận dữ liệu và thời gian commit.
- Throughput, số stream đồng thời và số phiên bị timeout.
- Số upload phải retry hoặc resume, số batch có record bị từ chối.

Dùng trace context để nối các thao tác trong một upload hoặc batch với những dịch vụ phụ thuộc. Không đưa **upload_id**, tên file, tenant ID hoặc user ID làm metric label nếu các giá trị này có cardinality cao. Có thể ghi một mã tham chiếu đã làm sạch trong log có kiểm soát để tra cứu một phiên cụ thể. Không ghi payload hoặc thông tin xác thực.

Phân biệt thời gian truyền dữ liệu với thời gian xử lý sau khi nhận đủ stream. Một RPC có thời gian dài có thể do client upload chậm, server ghi storage chậm hoặc bước commit tốn thời gian. Đo riêng các giai đoạn sẽ giúp xác định nút thắt.

## 14. Quyết định nhanh

| Nhu cầu | Lựa chọn |
|---|---|
| Gửi một payload nhỏ, kết quả xử lý ngay | Unary |
| Gửi file lớn theo chunk, chỉ cần kết quả sau khi nhận hết | Client streaming |
| Gửi nhiều record, chỉ cần tổng số thành công/thất bại ở cuối | Client streaming |
| Cần phản hồi hoặc xác nhận cho từng chunk trong khi vẫn gửi | Bidirectional streaming |
| Gửi một truy vấn rồi nhận danh sách kết quả dài | Server streaming |
| Cần tiếp tục upload sau khi mất kết nối | Client streaming kết hợp giao thức resume ở tầng ứng dụng |

Checklist trước khi đưa vào production:

- [ ] Hợp đồng quy định rõ message khởi tạo, chunk/record và response cuối.
- [ ] Có giới hạn kích thước mỗi message, tổng payload, số record và thời gian stream.
- [ ] Server xử lý tăng dần, không giữ toàn bộ payload lớn trong heap.
- [ ] Client và server có flow control phù hợp với tốc độ producer/consumer.
- [ ] Có checksum hoặc cơ chế xác minh tính toàn vẹn khi nghiệp vụ yêu cầu.
- [ ] Đã định nghĩa cancellation, cleanup, deadline và status.
- [ ] Đã xác định retry, idempotency, transaction và chính sách resume.
- [ ] Có kiểm thử stream lỗi, ngắt kết nối, tải đồng thời và giới hạn kích thước.
- [ ] TLS, xác thực, quota và logging an toàn đã được cấu hình.
- [ ] Metrics và trace giúp phân biệt thời gian truyền với thời gian xử lý.

Client streaming là lựa chọn phù hợp cho upload hoặc batch khi client gửi nhiều phần dữ liệu và server chỉ cần chốt một kết quả cuối. Chất lượng của giải pháp phụ thuộc vào hợp đồng stream rõ ràng, xử lý dữ liệu tăng dần, flow control, giới hạn tài nguyên và chính sách khôi phục khi RPC không hoàn tất.
