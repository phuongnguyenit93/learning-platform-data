# Tương thích dữ liệu

Trong các hệ thống dùng DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), dữ liệu thường được lưu trong cơ sở dữ liệu, tệp, kho đối tượng hoặc được trao đổi giữa các dịch vụ qua API, message queue và luồng sự kiện. Cấu trúc dữ liệu thay đổi theo thời gian khi sản phẩm bổ sung thuộc tính, đổi kiểu, chia module hoặc thay đổi quy tắc nghiệp vụ. **Tương thích dữ liệu** (*data compatibility*) là khả năng các phiên bản khác nhau của chương trình, schema và định dạng dữ liệu tiếp tục đọc, ghi, trao đổi hoặc diễn giải dữ liệu một cách đúng đắn theo hợp đồng đã xác định.

Ví dụ, phiên bản đầu của DSL định nghĩa:

```text
model Customer {
    id: String
    name: String
}
```

Sau một thời gian, hệ thống cần thêm email:

```text
model Customer {
    id: String
    name: String
    email: String?
}
```

Việc thêm `email` có thể tương thích với dữ liệu cũ nếu reader mới chấp nhận trường bị thiếu và có cách xử lý rõ ràng. Nhưng nếu đổi `id` từ `String` thành `Integer`, hoặc đổi ý nghĩa `name` mà vẫn giữ tên trường, dữ liệu cũ có thể không còn được đọc đúng.

Tương thích dữ liệu không chỉ là việc parser có đọc được một tệp hay không. Nó còn liên quan đến ý nghĩa của trường, đơn vị đo, nullability, default, thứ tự sự kiện, quy tắc xác thực, cách nâng cấp schema và khả năng nhiều phiên bản ứng dụng cùng hoạt động trong thời gian triển khai.

## 1. Dữ liệu, schema và hợp đồng

Để hiểu tương thích, cần phân biệt dữ liệu thực tế, schema mô tả dữ liệu và hợp đồng giữa các thành phần.

### 1.1. Dữ liệu

Dữ liệu là các giá trị được lưu hoặc truyền đi. Ví dụ:

```json
{
  "id": "C-1024",
  "name": "An"
}
```

Dữ liệu có thể tồn tại trong database, file JSON, message, event log hoặc cache.

### 1.2. Schema

Schema mô tả cấu trúc và ràng buộc của dữ liệu, chẳng hạn tên trường, kiểu, tính bắt buộc, giới hạn giá trị và quan hệ giữa các trường.

Ví dụ DSL:

```text
model Customer {
    id: String
    name: String
    age: Integer?
}
```

Schema có thể được dùng để kiểm tra dữ liệu, sinh mã, tạo bảng, tạo API contract hoặc sinh serializer/deserializer.

### 1.3. Hợp đồng dữ liệu

Hợp đồng dữ liệu (*data contract*) mô tả những điều producer cam kết cung cấp và consumer được phép giả định. Hợp đồng có thể bao gồm:

- Tên và kiểu của trường.
- Trường bắt buộc hay tùy chọn.
- Giá trị mặc định và cách diễn giải giá trị vắng mặt.
- Đơn vị đo, timezone, encoding và định dạng.
- Quy tắc null, enum và giá trị không nhận diện.
- Quy tắc thứ tự, tính duy nhất và tính ổn định của định danh.
- Ý nghĩa nghiệp vụ của từng trường.
- Chính sách phiên bản và thời gian hỗ trợ.

Hai schema có thể giống nhau về kiểu nhưng vẫn không tương thích về hợp đồng nếu ý nghĩa dữ liệu thay đổi. Ví dụ, trường `amount: Decimal` vẫn cùng kiểu sau khi hệ thống đổi đơn vị từ USD sang VND nhưng không cập nhật tên hoặc metadata. Consumer sẽ đọc được giá trị mà diễn giải sai.

## 2. Tương thích trong lưu trữ và trao đổi

Tương thích dữ liệu xuất hiện ở nhiều ranh giới khác nhau.

| Ranh giới | Câu hỏi tương thích |
|---|---|
| Ứng dụng và database | Phiên bản ứng dụng mới có đọc/ghi schema database hiện tại không? |
| Producer và consumer | Consumer có hiểu message do producer phiên bản mới gửi không? |
| File và chương trình | Phiên bản chương trình mới có đọc được file đã lưu từ phiên bản cũ không? |
| Event log | Consumer mới có replay được event lịch sử không? |
| API và client | Client cũ có tiếp tục hoạt động khi server đổi schema response không? |
| Cache | Dữ liệu cache cũ có còn hợp lệ theo schema và semantics mới không? |
| Backup và restore | Bản backup có thể được khôi phục bằng phiên bản phần mềm hiện tại không? |

Một thay đổi có thể tương thích ở ranh giới này nhưng không tương thích ở ranh giới khác. Ví dụ, thêm một trường tùy chọn có thể tương thích trong JSON nhưng lại cần migration database nếu cột mới được khai báo `NOT NULL` mà không có default.

## 3. Backward, forward và full compatibility

Ba khái niệm thường dùng để mô tả khả năng đọc dữ liệu giữa các phiên bản là backward compatibility, forward compatibility và full compatibility. Cần xác định rõ góc nhìn là reader hay writer, vì một số tài liệu có thể dùng thuật ngữ theo quy ước khác.

Giả sử có schema cũ `V1` và schema mới `V2`.

### 3.1. Backward compatibility

Theo quy ước phổ biến trong schema evolution, **backward compatible** nghĩa là reader mới có thể đọc dữ liệu được ghi theo schema cũ.

```text
Old writer (V1) ---> Data V1 ---> New reader (V2)
```

Ví dụ, V2 thêm trường tùy chọn `email`, còn dữ liệu V1 không có trường này. Reader V2 chấp nhận trường bị thiếu và xem nó là absent hoặc dùng default phù hợp.

### 3.2. Forward compatibility

**Forward compatible** nghĩa là reader cũ có thể đọc dữ liệu được ghi theo schema mới, thường bằng cách bỏ qua hoặc xử lý an toàn những phần chưa biết.

```text
New writer (V2) ---> Data V2 ---> Old reader (V1)
```

Ví dụ, writer V2 thêm trường `email`, còn reader V1 được thiết kế để bỏ qua trường không biết. Reader V1 vẫn đọc được `id` và `name`.

Không phải mọi định dạng đều tự động hỗ trợ hành vi này. Một parser strict có thể từ chối trường lạ; một protocol có quy tắc unknown-field preservation có thể giữ lại trường đó khi đọc rồi ghi lại.

### 3.3. Full compatibility

**Full compatibility** thường có nghĩa cả hai hướng đều được hỗ trợ:

- Reader mới đọc được dữ liệu cũ.
- Reader cũ đọc được dữ liệu mới.

Đây là mục tiêu hữu ích khi producer và consumer được nâng cấp độc lập hoặc triển khai cuốn chiếu.

### 3.4. Compatibility không chỉ là parse thành công

Một reader có thể parse dữ liệu mà không báo lỗi nhưng vẫn diễn giải sai. Ví dụ, V2 đổi `duration` từ giây sang mili giây nhưng vẫn giữ kiểu số nguyên. Reader V1 đọc được con số, song hành vi sai gấp 1.000 lần.

Vì vậy, cần đánh giá cả khả năng đọc cấu trúc lẫn khả năng giữ đúng ý nghĩa dữ liệu.

## 4. Compatibility của schema và compatibility của dữ liệu

Hai khái niệm có liên hệ nhưng khác nhau:

- **Schema compatibility:** schema mới có thể được sử dụng với reader/writer hoặc schema cũ theo một chính sách cụ thể không?
- **Data compatibility:** các bản ghi hoặc message thực tế có thể được diễn giải đúng qua phiên bản mới không?

Schema có thể tương thích về cấu trúc nhưng dữ liệu cũ vẫn vi phạm quy tắc mới. Ví dụ, schema V1 cho phép `age` từ 0 đến 150; schema V2 giới hạn 18 đến 120. Kiểu trường vẫn là integer, nhưng một số bản ghi cũ không còn hợp lệ.

Ngược lại, schema có thể thay đổi hình thức nhưng dữ liệu vẫn chuyển đổi được bằng migration rõ ràng. Ví dụ, đổi tên `fullName` thành `displayName` có thể được xử lý bằng migration hoặc mapping tương thích.

## 5. Các thay đổi schema thường gặp

Mỗi loại thay đổi có tác động khác nhau đến reader, writer, database và consumer.

### 5.1. Thêm trường tùy chọn

Schema cũ:

```text
model Customer {
    id: String
    name: String
}
```

Schema mới:

```text
model Customer {
    id: String
    name: String
    email: String?
}
```

Đây thường là thay đổi dễ tương thích nếu:

- Reader mới chấp nhận dữ liệu cũ thiếu `email`.
- Reader cũ có thể bỏ qua trường mới nếu cần đọc dữ liệu V2.
- Writer không bắt buộc mọi consumer cũ phải hiểu trường mới.
- Database migration tạo cột mới theo cách phù hợp.

### 5.2. Thêm trường bắt buộc

Nếu thêm:

```text
email: String
```

reader mới có thể từ chối bản ghi cũ không có `email`. Writer cũ cũng không biết phải cung cấp trường này.

Có thể cần:

- Giá trị mặc định có ý nghĩa.
- Migration backfill dữ liệu cũ.
- Giai đoạn cho phép trường vắng mặt.
- Chỉ chuyển sang bắt buộc sau khi mọi bản ghi đã được cập nhật.

Không nên đặt default giả tạo chỉ để migration qua được nếu giá trị đó làm sai ý nghĩa nghiệp vụ.

### 5.3. Xóa trường

Xóa trường có thể làm reader mới không còn nhìn thấy dữ liệu cũ. Reader cũ có thể vẫn mong đợi trường đó khi đọc dữ liệu do writer mới tạo.

Một quy trình an toàn thường gồm:

1. Đánh dấu trường deprecated.
2. Ngừng consumer mới sử dụng trường.
3. Xác nhận producer không còn ghi trường hoặc giữ ghi kép trong giai đoạn chuyển tiếp.
4. Triển khai reader tương thích.
5. Chỉ xóa vật lý sau khi các consumer cũ đã được nâng cấp và dữ liệu cần thiết đã được di chuyển.

### 5.4. Đổi tên trường

Đổi tên `name` thành `displayName` thường không phải thao tác đổi tên đơn giản đối với dữ liệu đã lưu. Reader cũ tìm `name`, reader mới tìm `displayName`.

Các chiến lược có thể gồm:

- Giữ alias đọc cho tên cũ.
- Tạm thời đọc cả hai tên với thứ tự ưu tiên rõ.
- Ghi cả hai tên trong giai đoạn chuyển đổi.
- Chạy migration sao chép dữ liệu rồi ngừng trường cũ.
- Dùng mapping ở lớp serialization để tách tên nội bộ và tên wire format.

Nếu cả hai trường cùng xuất hiện nhưng có giá trị khác nhau, cần quy tắc xác định giá trị nào có thẩm quyền.

### 5.5. Đổi kiểu trường

Đổi kiểu có thể là thay đổi nguy hiểm. Ví dụ:

```text
quantity: Integer
```

thành:

```text
quantity: Decimal
```

Một số reader có thể chuyển đổi an toàn, nhưng consumer cũ có thể giả định giá trị nguyên. Đổi từ `String` sang `Integer` còn có thể thất bại với dữ liệu không phải số.

Trước khi đổi kiểu, cần xác định:

- Tập giá trị hiện có.
- Quy tắc chuyển đổi và làm tròn.
- Overflow và giới hạn miền giá trị.
- Hành vi khi dữ liệu không hợp lệ.
- Khả năng đọc chéo giữa các phiên bản.

### 5.6. Thay đổi nullability

Đổi trường tùy chọn thành bắt buộc có thể làm dữ liệu cũ không hợp lệ. Đổi bắt buộc thành tùy chọn có thể ảnh hưởng consumer vốn giả định giá trị luôn tồn tại.

Null, absent và default cần được phân biệt. Một trường không xuất hiện trong JSON không nhất thiết tương đương trường xuất hiện với giá trị `null`.

### 5.7. Thêm giá trị enum

Schema V1:

```text
enum Status {
    PENDING
    PAID
}
```

Schema V2 thêm `REFUNDED`. Reader cũ có thể không biết giá trị mới. Nếu reader dùng switch exhaustive và từ chối enum lạ, dữ liệu mới sẽ làm consumer cũ lỗi.

Một protocol tương thích nên xác định cách xử lý enum chưa biết, chẳng hạn giá trị `UNKNOWN`, giữ nguyên raw value hoặc phát diagnostic mà vẫn bảo toàn dữ liệu.

### 5.8. Thay đổi cấu trúc lồng nhau

Di chuyển:

```text
customerName: String
```

thành:

```text
customer {
    name: String
}
```

là thay đổi cấu trúc lớn. Có thể cần adapter đọc/ghi, migration dữ liệu hoặc phiên bản schema mới. Việc chỉ đổi tên field trong DSL không tự chuyển các bản ghi đã lưu.

## 6. Bảng đánh giá thay đổi schema

Bảng dưới đây là hướng dẫn tổng quát. Kết quả thực tế phụ thuộc định dạng serialization, reader strict hay permissive và chính sách schema registry.

| Thay đổi | Reader mới đọc dữ liệu cũ | Reader cũ đọc dữ liệu mới | Lưu ý |
|---|---|---|---|
| Thêm trường optional | Thường có | Thường có nếu bỏ qua trường lạ | Cần quy tắc absent/default |
| Thêm trường required | Thường không nếu thiếu dữ liệu | Có thể nếu reader bỏ qua trường mới | Cần default hoặc backfill |
| Xóa trường | Có thể nếu reader không cần trường | Thường không nếu consumer cũ yêu cầu trường | Cần deprecate và chuyển đổi |
| Đổi tên trường | Không tự động | Không tự động | Thường tương đương xóa + thêm |
| Đổi kiểu | Tùy khả năng chuyển đổi | Tùy khả năng đọc kiểu mới | Cần kiểm tra dữ liệu và semantics |
| Required thành optional | Thường có | Có thể không an toàn với consumer giả định luôn có giá trị | Consumer phải xử lý absent/null |
| Thêm enum value | Có thể | Có thể thất bại nếu reader strict | Cần unknown-value handling |
| Đổi đơn vị đo | Parse được nhưng có thể sai nghĩa | Parse được nhưng có thể sai nghĩa | Cần metadata hoặc version/migration |
| Đổi timezone convention | Parse được nhưng có thể lệch thời gian | Tương tự | Cần quy ước UTC/offset rõ |

## 7. Null, absent và default

Ba trạng thái này thường bị nhầm lẫn nhưng có ý nghĩa khác nhau.

Giả sử schema:

```text
nickname: String?
```

Trong JSON, có thể gặp:

```json
{}
```

```json
{ "nickname": null }
```

```json
{ "nickname": "An" }
```

Chúng có thể mang nghĩa:

- **Absent:** producer không cung cấp trường.
- **Null:** producer cung cấp trường nhưng biểu thị không có giá trị.
- **Value:** producer cung cấp giá trị cụ thể.

Nếu schema có default, reader có thể áp dụng default khi absent. Nhưng có thể không áp dụng default khi explicit null. Quy tắc này cần được định nghĩa rõ.

### 7.1. Default ở reader và default ở writer

Default có thể được áp dụng ở hai thời điểm:

- **Reader default:** khi đọc dữ liệu thiếu trường, reader tự điền giá trị.
- **Writer default:** writer tự ghi giá trị mặc định vào dữ liệu.

Hai cách có thể tạo kết quả lưu trữ khác nhau. Reader default có thể giúp đọc dữ liệu cũ mà không cần migration ngay; writer default làm dữ liệu mới có trường rõ ràng.

### 7.2. Default phải ổn định về ý nghĩa

Nếu default thay đổi từ `currency = USD` sang `currency = EUR`, dữ liệu cũ không chứa trường currency có thể được diễn giải khác tùy phiên bản reader. Đây là thay đổi ngữ nghĩa dù schema không thay đổi cấu trúc.

Khi default có ý nghĩa quan trọng, cân nhắc materialize giá trị vào dữ liệu hoặc lưu schema version để reader biết default nào áp dụng.

## 8. Tương thích với các định dạng trao đổi

Mỗi định dạng serialization có quy tắc riêng về schema evolution và unknown fields.

### 8.1. JSON

JSON có cấu trúc object, array, string, number, boolean và null. JSON không tự mang một schema bắt buộc, nên ứng dụng thường dùng JSON Schema, OpenAPI hoặc model DSL để kiểm tra.

Một reader permissive có thể bỏ qua trường lạ:

```json
{
  "id": "C-1024",
  "name": "An",
  "email": "an@example.com"
}
```

Reader cũ chỉ dùng `id` và `name` vẫn có thể hoạt động nếu nó bỏ qua `email`. Nhưng một validator strict có thể từ chối trường không được khai báo.

JSON không quy định việc đổi kiểu hoặc ý nghĩa field có tương thích hay không. Điều đó do schema và ứng dụng quyết định.

### 8.2. Protocol Buffers

Protocol Buffers dùng field number để định danh trường trong wire format. Khi tiến hóa schema, field number đã dùng không được tái sử dụng cho trường khác. Trường đã xóa nên được `reserved` theo quy tắc của Protobuf để tránh diễn giải nhầm dữ liệu cũ.

Ví dụ minh họa:

```protobuf
message Customer {
  string id = 1;
  string name = 2;
  string email = 3;
}
```

Khi xóa field số `3`, nên giữ số và tên đó ở trạng thái reserved theo cú pháp Protobuf phù hợp. Thay đổi số field có thể làm dữ liệu wire bị diễn giải sai nghiêm trọng.

### 8.3. Avro

Avro hỗ trợ schema resolution giữa writer schema và reader schema. Reader có thể dùng default để xử lý trường mới hoặc trường vắng mặt theo các quy tắc cụ thể. Tính tương thích phụ thuộc cặp writer/reader schema và kiểu thay đổi.

### 8.4. XML

XML có thể được kiểm tra bằng XSD hoặc một schema tương đương. Thay đổi namespace, element name, attribute, cardinality hoặc type có thể ảnh hưởng consumer. Việc consumer bỏ qua element lạ phụ thuộc parser và policy.

### 8.5. CSV

CSV thường không mang metadata kiểu phong phú. Thay đổi thứ tự cột, tên header, dấu phân cách, encoding hoặc cách biểu diễn null có thể phá consumer.

Nếu dùng CSV để trao đổi lâu dài, nên có header rõ, quy định encoding, quoting, newline và schema version hoặc metadata đi kèm.

### 8.6. Database schema

Database có thể áp dụng ràng buộc như `NOT NULL`, unique, foreign key và check constraint. Một migration thêm cột required có thể thất bại trên bảng đã có dữ liệu nếu không có default/backfill phù hợp.

Schema database cũng cần tương thích với các phiên bản ứng dụng cùng tồn tại trong giai đoạn rollout.

## 9. Schema versioning

Versioning giúp producer và consumer biết dữ liệu được tạo theo hợp đồng nào.

Một số chiến lược:

- Version trong metadata của message hoặc file.
- Version trong tên topic hoặc endpoint.
- Schema ID được lưu cùng payload.
- Version của package/module trong dependency declaration.
- Version trong database migration history.

Ví dụ JSON:

```json
{
  "schemaVersion": 2,
  "id": "C-1024",
  "name": "An",
  "email": "an@example.com"
}
```

### 9.1. Version tường minh

Version tường minh giúp reader chọn adapter hoặc quy tắc giải mã phù hợp. Tuy nhiên, cần định nghĩa cách xử lý version chưa biết và chính sách hỗ trợ version cũ.

### 9.2. Schema registry

Schema registry là dịch vụ hoặc kho lưu trữ schema có version và ID. Producer có thể đăng ký schema, message chứa schema ID, consumer lấy schema tương ứng để giải mã hoặc kiểm tra compatibility.

Registry giúp tập trung quản lý schema, nhưng không tự bảo đảm semantics đúng. Cần có policy kiểm tra thay đổi trước khi publish schema mới.

### 9.3. Version của schema và version của ứng dụng

Schema version và application version không nhất thiết tăng cùng nhau. Một ứng dụng mới có thể vẫn dùng schema hiện tại; một schema mới có thể được nhiều ứng dụng cùng tiêu thụ.

Không nên giả định `appVersion = schemaVersion` nếu hai vòng đời thay đổi độc lập.

## 10. Chính sách compatibility trong schema registry

Registry hoặc công cụ quản lý schema có thể áp dụng các chính sách:

- **Backward:** schema mới có thể được reader mới dùng để đọc dữ liệu theo schema cũ.
- **Forward:** reader cũ có thể đọc dữ liệu được ghi theo schema mới.
- **Full:** hỗ trợ cả hai hướng.
- **Transitive:** kiểm tra compatibility với nhiều phiên bản trước đó, không chỉ phiên bản liền kề.
- **None:** không áp dụng kiểm tra compatibility tự động.

Tên gọi và cách thực hiện cụ thể phụ thuộc registry. Cần đọc đúng định nghĩa của công cụ đang dùng.

### 10.1. Non-transitive và transitive

Giả sử có V1, V2 và V3. V3 có thể tương thích với V2 nhưng không tương thích với V1. Nếu hệ thống vẫn còn message V1 trong event log, chỉ kiểm tra V3 với V2 là chưa đủ.

Transitive compatibility kiểm tra thay đổi với nhiều version trong lịch sử theo policy được chọn.

### 10.2. Lựa chọn policy

Một hệ thống xử lý event lưu lâu năm có thể cần policy nghiêm ngặt hơn một API nội bộ được nâng cấp đồng thời. Policy phải dựa trên vòng đời dữ liệu và khả năng cập nhật consumer.

## 11. Chiến lược migration dữ liệu

Khi thay đổi schema không thể đọc trực tiếp dữ liệu cũ, cần migration để chuyển dữ liệu sang dạng mới.

Migration là chương trình hoặc thao tác có kiểm soát để biến đổi dữ liệu đang lưu từ schema cũ sang schema mới.

Ví dụ đổi trường:

```text
fullName -> displayName
```

Một migration có thể:

1. Thêm cột `display_name`.
2. Sao chép giá trị từ `full_name` sang `display_name`.
3. Cập nhật ứng dụng đọc trường mới.
4. Cập nhật ứng dụng ghi trường mới.
5. Xác nhận dữ liệu đã chuyển đủ.
6. Ngừng sử dụng và sau đó xóa cột cũ.

### 11.1. Migration một bước

Một migration một bước có thể phù hợp khi hệ thống nhỏ, dừng dịch vụ được và dữ liệu không cần tương thích với phiên bản ứng dụng cũ.

Quy trình:

```text
Stop application
    -> backup
    -> migrate schema and data
    -> deploy new application
    -> verify
    -> resume traffic
```

### 11.2. Expand-and-contract

Với hệ thống cần hoạt động liên tục, chiến lược expand-and-contract giảm rủi ro khi nhiều phiên bản ứng dụng cùng tồn tại.

**Expand:** mở rộng schema để phiên bản cũ và mới đều có thể hoạt động. Ví dụ thêm cột mới nhưng vẫn giữ cột cũ.

**Migrate:** backfill dữ liệu cũ sang cột mới, có thể ghi kép trong thời gian chuyển đổi.

**Switch:** chuyển reader và writer sang trường mới sau khi dữ liệu đã sẵn sàng.

**Contract:** chỉ xóa trường cũ sau khi không còn consumer cần nó.

### 11.3. Backfill

Backfill là quá trình cập nhật các bản ghi hiện có để đáp ứng schema hoặc semantics mới. Backfill có thể chạy theo batch để tránh khóa bảng hoặc làm quá tải hệ thống.

Nên có checkpoint, khả năng tiếp tục sau lỗi và cách đếm số bản ghi đã xử lý.

### 11.4. Dual read và dual write

Trong giai đoạn chuyển đổi, ứng dụng có thể đọc cả trường cũ và mới, hoặc ghi cả hai.

Dual read cần quy tắc ưu tiên khi cả hai trường cùng tồn tại. Dual write cần xử lý trường hợp một lần ghi thành công còn lần ghi kia thất bại.

Không nên duy trì dual write lâu hơn cần thiết vì nó làm tăng số trạng thái có thể xảy ra và khó bảo đảm nhất quán.

## 12. Rollout nhiều phiên bản producer và consumer

Trong hệ thống phân tán, producer và consumer có thể được triển khai ở thời điểm khác nhau. Trong một khoảng thời gian, nhiều version cùng hoạt động.

Ví dụ:

```text
Producer V1 ----+
                +----> Message topic ----> Consumer V1
Producer V2 ----+                      \-> Consumer V2
```

Nếu producer V2 bắt đầu ghi trường mới trước khi mọi consumer được nâng cấp, consumer cũ phải có khả năng xử lý payload mới hoặc producer phải chờ đến khi consumer tương thích.

### 12.1. Consumer-first rollout

Một chiến lược phổ biến khi thêm field là:

1. Triển khai consumer mới có thể đọc cả dữ liệu cũ lẫn dữ liệu mới.
2. Chờ các consumer cũ được thay thế.
3. Triển khai producer mới bắt đầu ghi field mới.
4. Sau giai đoạn ổn định, ngừng hỗ trợ field cũ nếu cần.

### 12.2. Producer-first rollout

Producer-first chỉ an toàn nếu consumer hiện tại đã được thiết kế để bỏ qua hoặc xử lý dữ liệu mới. Nếu không, message mới có thể làm consumer cũ lỗi.

### 12.3. Rolling deployment

Trong rolling deployment, nhiều instance cũ và mới cùng nhận request. Schema và API cần tương thích trong toàn bộ khoảng thời gian này, không chỉ sau khi rollout hoàn tất.

### 12.4. Replay dữ liệu lịch sử

Consumer mới có thể phải đọc message được ghi từ nhiều năm trước. Compatibility cần tính đến dữ liệu lịch sử, không chỉ message mới được tạo hôm nay.

## 13. Tương thích trong API và event

API và event là hợp đồng trao đổi dữ liệu giữa các thành phần.

### 13.1. Thêm field vào response

Thêm field response thường tương thích với client bỏ qua field không biết. Nhưng client sinh code từ schema strict hoặc validator cấm additional properties có thể từ chối response mới.

### 13.2. Thêm field vào request

Thêm field tùy chọn vào request thường dễ tương thích hơn field bắt buộc. Nếu server mới yêu cầu field mới nhưng client cũ không gửi, request có thể thất bại.

### 13.3. Xóa field

Xóa field khỏi response có thể làm client cũ lỗi nếu client giả định trường luôn tồn tại. Xóa field khỏi request có thể làm server cũ hoặc gateway không còn nhận dạng payload.

### 13.4. Event bất biến

Event thường biểu diễn một sự kiện đã xảy ra trong quá khứ. Thay đổi ý nghĩa event cũ có thể phá replay và audit. Một nguyên tắc hữu ích là giữ semantics của event đã phát hành, bổ sung event mới hoặc versioned schema khi cần thay đổi lớn.

### 13.5. Command và event

Command thường là yêu cầu thực hiện hành động; event mô tả điều đã xảy ra. Quy tắc compatibility có thể khác nhau: command cần server hiểu trường gửi vào, còn event cần mọi consumer lịch sử có thể diễn giải payload đã phát.

## 14. Tương thích về ngữ nghĩa

Tương thích cấu trúc không bảo đảm tương thích ngữ nghĩa. Một số thay đổi nguy hiểm vì payload vẫn parse được.

### 14.1. Đơn vị đo

Trường:

```text
distance: Decimal
```

có thể ban đầu lưu mét rồi chuyển sang kilomet. Kiểu không đổi nhưng giá trị cần chuyển đổi hoặc metadata đơn vị phải rõ.

### 14.2. Tiền tệ

`amount: Decimal` chưa đủ nếu không biết currency. Thay đổi cách hiểu từ USD sang VND có thể làm sai số tiền dù schema vẫn hợp lệ. Nên biểu diễn amount cùng currency hoặc dùng kiểu miền mang đơn vị.

### 14.3. Thời gian

Timestamp cần quy định timezone, độ chính xác và cách xử lý thời gian không có offset. Chuyển từ local time sang UTC mà không chuyển đổi dữ liệu có thể làm lệch thời điểm.

### 14.4. Mã hóa và chuẩn hóa chuỗi

Thay đổi encoding, Unicode normalization hoặc quy tắc phân biệt hoa thường có thể ảnh hưởng khóa, tìm kiếm và so sánh dữ liệu.

### 14.5. Ý nghĩa enum

Giữ nguyên tên enum nhưng đổi ý nghĩa nghiệp vụ có thể làm consumer cũ xử lý sai. Nếu `CANCELLED` trước đây nghĩa là người dùng hủy nhưng nay bao gồm cả hệ thống tự hủy, cần đánh giá consumer dựa vào phân loại đó.

### 14.6. Thứ tự và tính duy nhất

Consumer có thể giả định danh sách được sắp xếp hoặc một trường là duy nhất. Nếu hợp đồng thay đổi các giả định này mà schema không đổi, hệ thống vẫn có thể bị lỗi.

## 15. Định danh trường và số field

Một số format dùng tên trường, một số dùng số hoặc tag ổn định.

### 15.1. Field name

JSON thường dùng tên field như `customerId`. Đổi tên field làm reader cũ không tìm thấy tên cũ, trừ khi có alias hoặc mapping.

### 15.2. Field number

Protocol Buffers dùng field number để xác định trường trong wire format. Field number đã phát hành phải được xem là định danh lâu dài.

### 15.3. Không tái sử dụng định danh

Nếu một field bị xóa, không nên dùng lại field number hoặc identifier cũ cho một ý nghĩa mới. Dữ liệu cũ vẫn có thể chứa identifier đó và bị diễn giải nhầm thành trường mới.

### 15.4. Stable identifier trong DSL

Một DSL có thể cho phép khai báo ID ổn định:

```text
model Customer {
    @fieldId(1) id: String
    @fieldId(2) name: String
}
```

ID này có thể được dùng khi sinh Protobuf, binary format hoặc schema registry. Cần xác định phạm vi duy nhất, quy tắc reserved và cách xử lý khi rename.

## 16. Data migration và rollback

Migration thay đổi dữ liệu thường khó hoàn tác hơn thay đổi code. Cần thiết kế đường rollback trước khi thực hiện.

### 16.1. Backup và restore

Trước migration có rủi ro, cần có backup có thể khôi phục và đã biết cách kiểm tra. Backup chưa được xác nhận restore không phải là bảo đảm phục hồi.

### 16.2. Migration một chiều

Một số biến đổi mất thông tin, ví dụ gộp hai trường vào một hoặc làm tròn số Decimal thành Integer. Không thể khôi phục dữ liệu gốc nếu không lưu thông tin bổ sung.

### 16.3. Roll-forward

Nếu migration không thể rollback an toàn, có thể sửa lỗi bằng migration tiến tiếp. Cần biết trạng thái schema và dữ liệu hiện tại để tạo bước sửa chính xác.

### 16.4. Idempotent migration

Migration idempotent có thể chạy lại mà không gây tác dụng phụ sai hoặc làm hỏng dữ liệu. Không phải mọi migration đều tự nhiên idempotent; cần thiết kế kiểm tra trạng thái, checkpoint và điều kiện thực hiện.

### 16.5. Tách schema migration và data migration

Thay đổi cấu trúc database và biến đổi hàng triệu bản ghi có thể được thực hiện ở hai bước khác nhau. Tách chúng giúp kiểm soát lock, thời gian chạy và khả năng tiếp tục khi lỗi.

## 17. Compatibility trong DSL và compiler

Một DSL có thể đưa thông tin tương thích trực tiếp vào schema hoặc metadata.

Ví dụ:

```text
schema Customer version 2 {
    id: String
    name: String
    email: String? @since(2)
}
```

Hoặc khai báo deprecation:

```text
model Customer {
    id: String

    @deprecated(since = "2", replacement = "displayName")
    name: String

    displayName: String?
}
```

Compiler có thể dùng metadata để:

- Phát warning khi code mới sử dụng trường cũ.
- Sinh serializer hỗ trợ cả tên cũ và mới trong giai đoạn chuyển đổi.
- Sinh migration script hoặc migration descriptor.
- Kiểm tra schema mới với các version được hỗ trợ.
- Sinh tài liệu thay đổi schema.
- Tạo adapter giữa model nội bộ và wire format.

### 17.1. Schema evolution rules

DSL có thể định nghĩa quy tắc tiến hóa:

```text
compatibility {
    mode = BACKWARD
    unknownFields = PRESERVE
    removedFieldIds = RESERVE
}
```

Đây là cú pháp minh họa. Compiler hoặc registry cần xác định ý nghĩa chính xác của từng tùy chọn và kiểm tra schema mới trước khi chấp nhận.

### 17.2. Adapter và mapping

Nếu schema nội bộ thay đổi nhưng wire format cần giữ ổn định, có thể dùng adapter:

```text
wire.customer_name <-> model.displayName
```

Adapter tách tên và cấu trúc bên ngoài khỏi model bên trong. Cần kiểm tra mapping hai chiều nếu cả đọc và ghi đều được hỗ trợ.

### 17.3. Versioned serializer

Serializer có thể chọn cách ghi theo version:

```text
serialize(customer, targetVersion = 1)
serialize(customer, targetVersion = 2)
```

Điều này hữu ích khi phải phục vụ consumer cũ trong thời gian chuyển đổi. Tuy nhiên, càng duy trì nhiều wire version thì chi phí bảo trì, kiểm thử và hỗ trợ càng tăng.

## 18. Quy trình thay đổi schema an toàn

Một thay đổi schema nên được xem xét theo vòng đời đầy đủ thay vì chỉ sửa model DSL.

Quy trình tham khảo:

1. Xác định mục tiêu thay đổi và semantics mới.
2. Liệt kê producer, consumer, database, file và event bị ảnh hưởng.
3. Phân loại backward/forward/full compatibility theo tình huống triển khai.
4. Kiểm tra dữ liệu hiện có và các giá trị ngoại lệ.
5. Chọn chiến lược versioning, adapter hoặc migration.
6. Triển khai reader có khả năng xử lý cả dạng cũ và mới nếu cần.
7. Mở rộng schema hoặc storage theo cách tương thích.
8. Backfill hoặc chuyển dữ liệu theo batch.
9. Chuyển producer sang dạng mới.
10. Theo dõi lỗi đọc/ghi và mức độ sử dụng trường cũ.
11. Ngừng trường cũ sau khi không còn consumer phụ thuộc.
12. Cập nhật tài liệu và compatibility policy.

Thứ tự cụ thể phụ thuộc hệ thống. Với thay đổi nhỏ trong một ứng dụng đơn khối, quy trình có thể đơn giản hơn; với event stream hoặc dịch vụ phân tán, cần tính đến nhiều version cùng tồn tại.

## 19. Kiểm thử tương thích dữ liệu

Kiểm thử compatibility cần xác nhận không chỉ schema hợp lệ mà còn các producer/consumer thực tế hoạt động đúng.

### 19.1. Schema compatibility test

So sánh schema mới với schema đã phát hành để phát hiện thay đổi bị cấm theo policy. Có thể kiểm tra field thêm/xóa, kiểu, default, enum và field identifier.

### 19.2. Golden data

Lưu các payload mẫu từ những phiên bản trước và kiểm tra reader hiện tại có thể đọc chúng đúng không.

Ví dụ:

```text
fixtures/
├── customer-v1.json
├── customer-v2.json
└── customer-v3.json
```

Các fixture này giúp phát hiện trường hợp schema mới parse được nhưng diễn giải sai dữ liệu lịch sử.

### 19.3. Cross-version tests

Kiểm tra các cặp:

- Writer cũ với reader mới.
- Writer mới với reader cũ.
- Writer mới với reader mới.
- Reader mới với dữ liệu của nhiều phiên bản cũ.

Không phải mọi cặp đều cần hỗ trợ, nhưng policy phải nói rõ cặp nào được cam kết.

### 19.4. Round-trip tests

Đọc dữ liệu rồi ghi lại có thể làm mất unknown fields, thứ tự hoặc metadata. Round-trip test kiểm tra những thông tin cần bảo toàn vẫn tồn tại sau chu trình deserialize/serialize.

### 19.5. Migration tests

Kiểm thử migration trên dữ liệu đại diện gồm dữ liệu bình thường, null, absent, giá trị biên và bản ghi lỗi. Cần kiểm tra số lượng bản ghi trước/sau và các invariant nghiệp vụ.

### 19.6. Contract tests

Producer và consumer có thể kiểm tra hợp đồng độc lập. Producer xác nhận payload tuân theo schema; consumer xác nhận mình có thể xử lý những payload mà hợp đồng cho phép.

### 19.7. Test semantics

Kiểm tra đơn vị, timezone, tiền tệ, enum và thứ tự dữ liệu. Đây là những trường hợp có thể không bị schema validator phát hiện.

## 20. Observability khi tiến hóa dữ liệu

Trong quá trình rollout, cần theo dõi:

- Tỷ lệ message theo schema version.
- Số lần deserialize thất bại.
- Tỷ lệ bản ghi thiếu trường mới.
- Số consumer vẫn đọc trường cũ.
- Tiến độ backfill.
- Số bản ghi bị reject bởi validation.
- Độ trễ xử lý và số lần retry.
- Số lượng event lịch sử còn dùng schema cũ.

Các metric giúp quyết định khi nào có thể chuyển sang giai đoạn tiếp theo hoặc xóa trường cũ.

### 20.1. Không log dữ liệu nhạy cảm

Diagnostic và log migration nên ghi schema version, record ID đã được bảo vệ và loại lỗi. Không nên ghi password, token hoặc toàn bộ dữ liệu cá nhân nếu không cần thiết.

### 20.2. Dead-letter queue

Message không thể giải mã hoặc không hợp lệ có thể được đưa vào dead-letter queue để điều tra. Cần lưu thông tin schema version, lỗi và nguồn gốc message, đồng thời bảo vệ payload theo chính sách dữ liệu.

## 21. Các ví dụ tương thích

### 21.1. Thêm trường tùy chọn vào JSON

V1:

```json
{
  "id": "C-1024",
  "name": "An"
}
```

V2:

```json
{
  "id": "C-1024",
  "name": "An",
  "email": "an@example.com"
}
```

Reader V2 có thể xử lý payload V1 bằng cách xem `email` là absent. Reader V1 có thể xử lý payload V2 nếu bỏ qua unknown field. Đây là trường hợp có khả năng full compatibility với reader permissive.

### 21.2. Đổi tên field bằng giai đoạn chuyển tiếp

V1 dùng `name`, V2 muốn dùng `displayName`. Trong thời gian chuyển đổi, writer có thể ghi cả hai:

```json
{
  "name": "An",
  "displayName": "An"
}
```

Reader mới ưu tiên `displayName`, fallback sang `name`. Sau khi tất cả consumer được nâng cấp và dữ liệu đã được backfill, có thể ngừng `name`.

Nếu hai trường có giá trị khác nhau, cần một quy tắc authoritative field rõ ràng và metric để phát hiện dữ liệu lệch.

### 21.3. Đổi đơn vị thời gian

V1:

```json
{ "timeout": 30 }
```

Giả sử V1 hiểu timeout theo giây. Nếu V2 muốn dùng mili giây, không nên giữ nguyên tên và chỉ thay semantics. Có thể đổi tên thành `timeoutMs`, thêm unit metadata hoặc version schema rõ ràng, rồi chuyển đổi dữ liệu.

### 21.4. Thêm enum value

V1:

```text
Status = PENDING | PAID
```

V2:

```text
Status = PENDING | PAID | REFUNDED
```

Consumer cũ cần có chiến lược với `REFUNDED`: bỏ qua an toàn nếu nghiệp vụ cho phép, ánh xạ sang `UNKNOWN`, giữ raw value hoặc từ chối với diagnostic rõ. Chọn cách nào phụ thuộc việc consumer có cần phân biệt trạng thái mới hay không.

## 22. Những sai lầm thường gặp

**Cho rằng parse thành công đồng nghĩa tương thích.** Dữ liệu có thể parse được nhưng sai đơn vị, timezone hoặc ý nghĩa nghiệp vụ.

**Thêm trường required mà không backfill.** Reader mới có thể từ chối dữ liệu cũ hoặc database migration thất bại.

**Đổi tên field như thể chỉ là refactor code.** Payload và dữ liệu lưu trữ cũ vẫn mang tên cũ; cần alias, adapter hoặc migration.

**Tái sử dụng field number hoặc identifier đã xóa.** Dữ liệu lịch sử có thể bị diễn giải thành trường mới với ý nghĩa sai.

**Không phân biệt absent, null và default.** Ba trạng thái có thể có semantics khác nhau và ảnh hưởng quá trình tiến hóa schema.

**Chỉ kiểm tra version liền kề.** Event log hoặc file archive có thể chứa dữ liệu từ nhiều version cũ hơn.

**Triển khai producer mới trước consumer cũ mà không kiểm tra forward compatibility.** Consumer cũ có thể từ chối payload mới.

**Xóa trường cũ quá sớm.** Một consumer chưa được nâng cấp hoặc một job replay lịch sử vẫn có thể cần trường đó.

**Thay đổi đơn vị nhưng giữ nguyên kiểu và tên.** Schema validator có thể không phát hiện lỗi diễn giải.

**Không kiểm thử migration trên dữ liệu thực tế đại diện.** Giá trị null, ngoại lệ hoặc dữ liệu cũ bất thường có thể làm migration thất bại.

## 23. Ghi nhớ

- Tương thích dữ liệu là khả năng các phiên bản schema, producer, consumer và chương trình tiếp tục đọc, ghi và diễn giải dữ liệu đúng theo hợp đồng.
- Backward compatibility thường nói reader mới đọc dữ liệu cũ; forward compatibility nói reader cũ đọc dữ liệu mới; full compatibility hỗ trợ cả hai hướng.
- Schema compatibility không bảo đảm semantics tương thích; đơn vị đo, timezone, currency và ý nghĩa enum cũng cần được giữ đúng.
- Thêm trường optional thường dễ tương thích hơn thêm trường required; đổi tên và đổi kiểu cần chiến lược rõ.
- Absent, null và default là các trạng thái khác nhau nếu hợp đồng quy định như vậy.
- Mỗi serialization format có quy tắc evolution riêng; cần tôn trọng field identifier và unknown-field behavior.
- Schema versioning và schema registry giúp nhận diện hợp đồng, nhưng cần policy kiểm tra thay đổi.
- Migration có thể cần expand-and-contract, backfill, dual read/write và kế hoạch rollback hoặc roll-forward.
- Producer và consumer thường tồn tại nhiều version cùng lúc trong rolling deployment.
- Kiểm thử cần gồm schema compatibility, golden data, cross-version, round-trip, migration và semantic tests.
- DSL/compiler có thể hỗ trợ metadata deprecation, schema version, adapter, migration descriptor và serializer theo version.

## 24. Câu hỏi tự kiểm tra

1. Tương thích dữ liệu khác tương thích schema ở điểm nào?
2. Backward, forward và full compatibility được hiểu như thế nào theo góc nhìn reader/writer?
3. Vì sao thêm một trường optional thường dễ tương thích hơn thêm trường required?
4. Khi đổi tên trường, những chiến lược nào giúp reader và writer cũ/mới cùng hoạt động?
5. Phân biệt absent, null và default. Reader nên xử lý chúng ra sao?
6. Vì sao thêm enum value có thể làm consumer cũ lỗi dù cấu trúc message không đổi?
7. Tại sao không được tái sử dụng field number đã phát hành trong Protocol Buffers?
8. Schema registry giúp quản lý compatibility như thế nào? Registry không giải quyết được vấn đề semantics nào?
9. Expand-and-contract gồm những giai đoạn nào?
10. Vì sao consumer-first rollout thường an toàn khi thêm field mới?
11. Nêu ví dụ thay đổi schema không làm parse thất bại nhưng khiến dữ liệu bị diễn giải sai.
12. Golden data và round-trip test giúp phát hiện những lỗi nào?
13. Khi nào cần transitive compatibility thay vì chỉ kiểm tra version liền kề?
14. Hãy đề xuất một kế hoạch tương thích khi đổi `fullName` thành `displayName` trong hệ thống có nhiều consumer và dữ liệu lưu lâu dài.
