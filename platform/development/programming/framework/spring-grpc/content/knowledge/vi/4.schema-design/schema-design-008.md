# Xóa field bằng reserved

Khi một field trong Protocol Buffers không còn được sử dụng, xóa dòng khai báo khỏi file `.proto` vẫn chưa đủ. Số field đã phát hành có thể còn xuất hiện trong request cũ, dữ liệu lưu trữ hoặc event được phát lại. Nếu một nhà phát triển sau này vô tình dùng lại số đó cho ý nghĩa khác, protobuf có thể giải mã dữ liệu cũ thành một field mới mà không báo lỗi rõ ràng.

Trong **Spring gRPC**, điều này ảnh hưởng cả hợp đồng trên wire lẫn mã Java sinh từ schema. Cách bảo vệ là dùng từ khóa `reserved` để giữ lại số field và tên field đã ngừng sử dụng. Bài này tập trung vào cú pháp, thời điểm áp dụng và cách kiểm tra việc xóa field an toàn.

## 1. Vì sao phải reserved sau khi xóa?

Protobuf binary nhận diện field bằng **field number** và wire type, không dựa vào tên field. Giả sử phiên bản cũ khai báo:

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
  string legacy_description = 3;
}
```

Sau khi xóa `legacy_description`, một phiên bản schema mới có thể trông như sau:

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
}
```

Nếu số 3 không được đánh dấu, người khác có thể vô tình khai báo `int64 supplier_id = 3;`. Một client cũ gửi `legacy_description` với tag 3; server mới lại diễn giải tag đó thành `supplier_id` nếu wire type phù hợp. Kết quả có thể là dữ liệu sai mà không có lỗi parse dễ nhận biết.

`reserved` tạo một rào chắn ở bước biên dịch schema: compiler từ chối việc tái sử dụng số hoặc tên đã đánh dấu trong cùng message. Có hai thứ cần bảo vệ:

- **Field number** bảo vệ dữ liệu protobuf binary khỏi bị diễn giải theo ý nghĩa mới.
- **Field name** bảo vệ định danh trong schema, mã nguồn, descriptor và các cách biểu diễn dựa trên tên như ProtoJSON hoặc TextFormat.

Vì vậy, khi xóa field đã phát hành, thông lệ an toàn là reserve **cả số lẫn tên**.

## 2. Cú pháp reserved trong message

Đưa số và tên vào hai khai báo `reserved` riêng:

```proto
message Product {
  reserved 3, 7 to 9;
  reserved "legacy_description", "old_price";

  string product_id = 1;
  string display_name = 2;
  string summary = 10;
}
```

Trong ví dụ:

- `3` là số field đã xóa.
- `7 to 9` là một dải số đã dành riêng; hai đầu mút đều được tính.
- `legacy_description` và `old_price` là các tên field đã ngừng sử dụng.
- `summary = 10` dùng số mới chưa bị reserve.

**Không trộn số và tên trong cùng một câu lệnh `reserved`.** Hãy viết một câu cho danh sách số hoặc dải số, và một câu khác cho danh sách tên. Các khai báo này thuộc phạm vi của message chứa chúng; reserve số 3 trong `Product` không tự động reserve số 3 trong một message khác.

Có thể reserve đến số lớn nhất bằng `to max`:

```proto
message LegacyPayload {
  reserved 20 to max;
  reserved "obsolete_value";

  string id = 1;
}
```

Chỉ dùng dải rộng khi toàn bộ số trong dải thực sự đã được sử dụng hoặc cần bảo vệ. Không reserve một khoảng bao trùm các field đang tồn tại; cũng không xóa field đang được dùng chỉ để làm cho câu lệnh `reserved` biên dịch được.

### Xóa field và thay bằng field mới

Nếu `legacy_description = 3` được thay bằng `summary = 10`, schema cuối cùng cần giữ tag và tên cũ:

```proto
message Product {
  reserved 3;
  reserved "legacy_description";

  string product_id = 1;
  string display_name = 2;
  string summary = 10;
}
```

Không đổi `summary` thành số 3 chỉ vì field cũ đã được dọn khỏi source. Mục tiêu của `reserved` chính là ngăn việc dùng lại số đó.

## 3. Reserved cho enum value

Enum cũng có số value trên wire. Nếu xóa một giá trị enum đã phát hành, hãy reserve cả số và tên:

```proto
enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;

  reserved 3, 7 to 9;
  reserved "PRODUCT_STATE_LEGACY";
}
```

Ví dụ này giả định các số 3 và 7–9 cùng tên `PRODUCT_STATE_LEGACY` đã từng được dùng rồi mới bị loại bỏ. Không tái sử dụng số 2 cho trạng thái khác chỉ vì enum value `PRODUCT_STATE_ARCHIVED` đã bị xóa; số đó vẫn phải được giữ lại nếu đã phát hành.

Khi consumer Java nhận một enum number mà phiên bản generated code của nó không biết, proto3 có thể biểu diễn trạng thái đó bằng `UNRECOGNIZED` và vẫn cho phép đọc giá trị số nguyên. Vì vậy, thêm enum value mới cũng cần đánh giá khả năng xử lý của client cũ; reserve chỉ bảo vệ các value đã xóa khỏi bị dùng lại.

## 4. Quy trình xóa field an toàn

Không nên xóa field chỉ vì đã sửa xong một nơi trong code. Trước hết cần biết ai còn gửi, đọc hoặc lưu dữ liệu đó.

1. **Xác nhận field hết vòng đời.** Tìm các client, server, consumer event, dữ liệu lưu trữ, báo cáo và FieldMask path còn tham chiếu field.
2. **Đánh dấu deprecated nếu cần giai đoạn chuyển tiếp.** Có thể dùng option `[deprecated = true]` để cảnh báo khi field còn khai báo:

   ```proto
   message Product {
     string legacy_description = 3 [deprecated = true];
   }
   ```

   `deprecated = true` chỉ là tín hiệu cho tooling và người phát triển; nó không tự ngừng truyền dữ liệu, không xóa field và không ngăn code sử dụng field.
3. **Ngừng ghi và di chuyển consumer.** Server có thể ngừng phát giá trị cũ sau khi client đã có cách đọc field thay thế. Nếu có field mới thay thế, duy trì dual-read/dual-write trong thời gian được xác định và tránh hai nguồn dữ liệu mâu thuẫn.
4. **Xóa khai báo khi không còn phụ thuộc.** Gỡ field cũ khỏi message hoặc enum sau khi các bên liên quan đã chuyển đổi theo kế hoạch.
5. **Reserve số và tên.** Thêm `reserved` trong đúng message/enum chứa field đã xóa.
6. **Sinh lại mã và kiểm tra.** Cập nhật các Java handler, mapper, test và consumer; kiểm tra schema mới không vô tình tái sử dụng tag cũ.

Nếu field chưa từng được phát hành ra ngoài và chưa có dữ liệu được serialize/lưu lại, việc xóa có thể đơn giản hơn. Nhưng với hợp đồng đã phát hành, không nên suy luận rằng field không còn được dùng chỉ vì một repository không còn tham chiếu đến nó.

## 5. `reserved` bảo vệ điều gì và không bảo vệ điều gì?

| Trường hợp | `reserved` có tác dụng? | Giải thích |
| --- | --- | --- |
| Nhà phát triển thêm field mới dùng lại số đã reserve trong cùng message | **Có** | `protoc` từ chối schema |
| Nhà phát triển dùng lại tên field đã reserve trong cùng message | **Có** | Compiler từ chối tên đã dành riêng |
| Client cũ vẫn gửi tag của field đã xóa tới server mới | **Không chặn ở runtime** | Server mới thường coi tag đó là unknown field và bỏ qua |
| Dữ liệu cũ bị diễn giải thành field mới do tái sử dụng số trong một schema khác | **Ngăn từ phía schema có reserve** | `reserved` không phải bộ lọc kiểm tra payload tùy ý |
| Client Java còn gọi accessor của field đã xóa | **Không tự sửa mã client** | Generated API mới không còn accessor; mã nguồn phụ thuộc sẽ cần cập nhật |
| JSON client còn gửi tên field cũ | **Không bảo đảm mọi JSON parser xử lý giống nhau** | Cần kiểm tra ProtoJSON/gateway và chính sách unknown key riêng |

Điểm quan trọng: `reserved` là **quy tắc ở schema/compile time**, không phải lệnh runtime để server trả lỗi khi nhận tag cũ. Khi server mới parse binary request có field cũ, field đó có thể bị xem là unknown. Do đó, nếu ứng dụng cần phát hiện client còn dùng field cũ, phải có kế hoạch đo lường hoặc chuyển đổi trước khi xóa; không trông chờ `reserved` làm việc đó.

Trong Java protobuf, generated message có cơ chế lưu unknown fields. Tuy nhiên, không nên dựa vào việc unknown field luôn được bảo toàn qua mọi tầng xử lý: chuyển đổi sang DTO khác, dựng lại message, serialize JSON hoặc đi qua gateway có thể làm mất thông tin không được schema nhận diện.

## 6. Tác động đến Spring gRPC và các client

Khi field bị xóa khỏi `.proto` và mã Java được sinh lại:

- Accessor như `getLegacyDescription()` và builder `setLegacyDescription(...)` không còn trong generated class mới. Các module Java còn gọi chúng sẽ không biên dịch cho đến khi được cập nhật.
- Server mới không còn tạo field đó trong response. Client cũ vẫn có thể parse các field còn lại, nhưng getter cũ có thể trả giá trị mặc định.
- Client cũ tiếp tục gửi field đã xóa dưới dạng binary; server mới có thể bỏ qua field unknown. Việc RPC trả `OK` không chứng minh dữ liệu cũ đã được xử lý.
- Các đường dẫn FieldMask, mapping DTO, ProtoJSON key, log hoặc consumer event có tham chiếu tên cũ cần được di chuyển riêng.

`reserved` không đổi tên service, RPC hay package. Nó cũng không tự tạo API mới. Nếu việc xóa field làm thay đổi hành vi mà client đang phụ thuộc, hãy dùng một giai đoạn chuyển tiếp hoặc version API phù hợp thay vì chỉ sửa schema rồi phát hành đồng loạt.

### Ví dụ trước và sau

**Trước khi xóa:**

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
  string legacy_description = 3;
}
```

**Sau khi xóa:**

```proto
message Product {
  reserved 3;
  reserved "legacy_description";

  string product_id = 1;
  string display_name = 2;
  string summary = 10;
}
```

Client mới dùng `summary`; server không còn đọc/ghi `legacy_description`. Các client cũ cần được di chuyển trước hoặc được hỗ trợ trong giai đoạn chuyển tiếp. Số 3 và tên cũ vẫn nằm trong schema dưới dạng reserved để không ai vô tình tái sử dụng.

## 7. Kiểm tra sau khi xóa

Một lần review schema nên xác nhận:

- `reserved` nằm trong đúng message hoặc enum.
- Mỗi field đã xóa có cả số và tên được reserve; các dải số dùng đúng phạm vi và không bao trùm field đang tồn tại.
- Không có field hoặc enum value hiện tại trùng số/tên đã reserve.
- Field thay thế dùng số mới, không chiếm tag cũ.
- Các Java accessor, mapper, FieldMask path và consumer liên quan đã được cập nhật.
- Client cũ gửi payload có field đã xóa vẫn có hành vi được dự kiến; không nhầm việc parse thành công với việc dữ liệu được áp dụng.
- JSON gateway và ProtoJSON đã được kiểm tra nếu API hỗ trợ các dạng này.

Các test hữu ích:

| Test | Điều cần xác minh |
| --- | --- |
| Biên dịch schema mới | `protoc` chấp nhận các khai báo reserved hợp lệ |
| Thử khai báo lại field number đã reserve | Compiler từ chối |
| Thử khai báo lại field name đã reserve | Compiler từ chối |
| Parse fixture binary từ schema cũ bằng schema mới | Các field còn tồn tại vẫn giữ đúng giá trị; tag cũ không bị gán nhầm sang field mới |
| Gọi server mới bằng client cũ | RPC có hành vi chuyển tiếp đã công bố; field cũ không bị âm thầm diễn giải thành dữ liệu khác |
| Biên dịch các module Java phụ thuộc | Không còn accessor của field đã xóa |
| Kiểm thử ProtoJSON/FieldMask | Không còn phụ thuộc ngoài ý muốn vào tên cũ |

Không cần viết test để chứng minh `reserved` tự từ chối tag cũ ở runtime: đó không phải chức năng của nó. Điều cần chứng minh là schema mới không thể tái sử dụng số/tên cũ và hệ thống đã chuyển đổi mọi nơi còn phụ thuộc field.

## 8. Tự kiểm tra

**Câu 1.** Một message đã phát hành có `string old_code = 5;`. Sau khi xóa field này, schema mới nên khai báo gì?

**Đáp án:** `reserved 5;` và `reserved "old_code";` trong đúng message đó. Không dùng số 5 cho field khác.

**Câu 2.** `reserved 4 to 8;` bao gồm những số nào?

**Đáp án:** Bao gồm cả hai đầu mút: 4, 5, 6, 7 và 8.

**Câu 3.** Client cũ gửi field number đã bị xóa tới server mới. `reserved` có khiến server tự trả `INVALID_ARGUMENT` không?

**Đáp án:** Không. `reserved` ngăn schema tương lai khai báo lại số/tên đó. Server mới thường xem tag cũ là unknown field; muốn phát hiện client cũ còn gửi field phải có biện pháp quan sát/chuyển đổi riêng.

**Câu 4.** Có thể chỉ reserve số mà không reserve tên không?

**Đáp án:** Cú pháp cho phép, nhưng với field đã phát hành nên reserve cả số và tên. Số bảo vệ wire format; tên bảo vệ việc tái sử dụng định danh trong schema và các cách biểu diễn dựa trên tên.

**Câu 5.** Field đã đánh dấu `[deprecated = true]` có thể xóa ngay không?

**Đáp án:** Không nên mặc định như vậy. Deprecated chỉ là cảnh báo, không chứng minh consumer đã ngừng sử dụng. Cần xác nhận việc chuyển đổi, sau đó mới xóa khai báo và reserve số/tên.

Khi xóa field đã phát hành, hãy giữ lại dấu vết của nó bằng `reserved`. Quy tắc nhỏ này ngăn một thay đổi tưởng như vô hại trong schema hôm nay trở thành lỗi giải mã dữ liệu khó phát hiện ở client, server hoặc consumer trong tương lai.
