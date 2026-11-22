# Di trú schema

Trong một hệ thống sử dụng ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), schema mô tả cấu trúc dữ liệu mà chương trình có thể đọc, tạo, kiểm tra hoặc trao đổi với hệ thống khác. Schema có thể định nghĩa record, field, kiểu dữ liệu, quan hệ, constraint, event payload, API contract hoặc cấu trúc lưu trữ. Khi yêu cầu nghiệp vụ thay đổi, schema cũng phải thay đổi. **Di trú schema (schema migration)** là quá trình đưa schema và dữ liệu đang tồn tại từ một phiên bản sang phiên bản mới theo cách có kiểm soát.

Ví dụ, phiên bản đầu của Order có field customerCode kiểu String. Phiên bản sau muốn dùng customerId với kiểu định danh riêng, bổ sung currency và tách địa chỉ giao hàng thành một record. Thay đổi này ảnh hưởng đến dữ liệu cũ, chương trình DSL, query, API, event consumer, workflow đang chạy và các artifact đã được triển khai. Chỉ sửa khai báo schema là chưa đủ; hệ thống cần biết dữ liệu cũ được chuyển đổi thế nào và những thành phần nào còn tương thích.

Một chiến lược migration tốt xác định rõ source version, target version, phạm vi dữ liệu, thứ tự triển khai, tính tương thích, cách kiểm tra kết quả và phương án phục hồi. Với hệ thống lớn, migration thường diễn ra theo nhiều giai đoạn để phiên bản cũ và mới cùng hoạt động trong một khoảng thời gian. Với workflow dài hạn, instance có thể vẫn giữ context theo schema cũ trong khi definition mới đã được phát hành.

Bài học này trình bày vai trò của schema trong DSL, các loại thay đổi, versioning, backward và forward compatibility, migration plan, chuyển đổi dữ liệu, expand-and-contract, migration DSL, transaction, rollback, event và API schema, workflow context, validation, testing, vận hành và các ví dụ thực tế.

## 1. Schema và schema migration là gì?

Schema là hợp đồng cấu trúc và quy tắc cho dữ liệu. Nó cho biết dữ liệu gồm những field nào, kiểu của từng field, field nào bắt buộc, constraint nào phải đúng và các giá trị liên hệ với nhau ra sao.

Ví dụ:

~~~text
record Customer {
  id: CustomerId
  name: String
  email: String?
  createdAt: Instant
}

record Order {
  id: OrderId
  customerId: CustomerId
  total: Decimal
  status: OrderStatus
}
~~~

Schema migration là quá trình thay đổi hợp đồng này và đưa các thành phần phụ thuộc sang trạng thái tương thích với phiên bản mới.

### 1.1. Schema có thể xuất hiện ở nhiều tầng

Trong hệ sinh thái DSL, schema có thể mô tả:
- Domain model và record.
- Input và output của function.
- Query result.
- Event payload.
- API request và response.
- Database table.
- File import/export.
- Workflow context.
- Artifact manifest.

Một thay đổi ở domain model có thể lan đến nhiều schema khác. Cần lập dependency graph để biết những thành phần nào bị ảnh hưởng.

### 1.2. Migration không chỉ là đổi tên field

Migration có thể bao gồm:
- Thêm hoặc xóa field.
- Đổi tên field.
- Đổi kiểu dữ liệu.
- Thay đổi nullability.
- Đổi enum value.
- Tách hoặc gộp record.
- Thay đổi quan hệ.
- Thêm constraint.
- Thay đổi đơn vị hoặc ý nghĩa nghiệp vụ.
- Chuyển dữ liệu sang cấu trúc mới.

Đổi kiểu từ String sang CustomerId có thể cần parse và kiểm tra dữ liệu. Đổi đơn vị từ cents sang Decimal tiền tệ cần chuyển đổi giá trị, không chỉ thay type.

### 1.3. Schema migration và code migration

Schema migration thay đổi cấu trúc hoặc dữ liệu. Code migration thay đổi chương trình DSL để sử dụng schema mới. Hai việc thường đi cùng nhau nhưng có vòng đời và cách kiểm tra khác nhau.

### 1.4. Schema version và data version

Schema version mô tả phiên bản hợp đồng. Data version mô tả dữ liệu đã được chuyển đổi đến mức nào. Trong một số hệ thống, chúng trùng nhau; trong hệ thống khác, dữ liệu có thể được chuyển dần và chứa nhiều version trong cùng giai đoạn.

### 1.5. Migration là thay đổi có trạng thái

Một migration có thể:
- Chưa được lên kế hoạch.
- Đã được chuẩn bị.
- Đang chạy.
- Hoàn tất.
- Thất bại.
- Cần tiếp tục.
- Đã được phục hồi hoặc thay thế.

Lưu trạng thái và lịch sử migration giúp tránh chạy lặp một thao tác không idempotent.

## 2. Vì sao schema thay đổi?

Schema thay đổi khi miền nghiệp vụ, tích hợp hoặc yêu cầu kỹ thuật thay đổi.

### 2.1. Nghiệp vụ mở rộng

Một Order ban đầu chỉ có total, sau đó cần lưu currency, tax breakdown, promotion và shipment address. Schema phải biểu diễn các khái niệm mới.

### 2.2. Chuẩn hóa dữ liệu

Một field text có thể được tách thành cấu trúc có kiểu rõ ràng. Ví dụ fullName được tách thành givenName và familyName. Việc tách cần quy tắc xử lý dữ liệu không thể phân chia chính xác.

### 2.3. Chất lượng dữ liệu

Một field từng optional có thể trở thành required sau khi dữ liệu được làm sạch và quy trình nhập liệu được cập nhật.

### 2.4. Tích hợp hệ thống

API bên ngoài có thể đổi payload, enum hoặc version. DSL mapping cần tương thích với schema nguồn và schema đích.

### 2.5. Hiệu năng và lưu trữ

Có thể tách bảng lớn, thêm index, đổi representation hoặc partition. Đây là migration cấu trúc lưu trữ, có thể không thay đổi public domain schema.

### 2.6. Bảo mật và quyền riêng tư

Một field nhạy cảm có thể được tách sang vùng lưu trữ có quyền hạn chặt hơn, mã hóa hoặc retention riêng. Migration cần xử lý cả dữ liệu cũ và bản sao trong log/cache.

## 3. Phân loại thay đổi schema

Phân loại thay đổi giúp dự đoán mức độ tương thích.

| Thay đổi | Ví dụ | Rủi ro thường gặp |
| --- | --- | --- |
| Additive | Thêm field optional | Consumer cũ có thể bỏ qua hoặc không hiểu field |
| Rename | customerCode thành customerId | Code cũ không tìm thấy field |
| Removal | Xóa legacyNote | Consumer cũ vẫn yêu cầu field |
| Type change | String thành Decimal | Dữ liệu không parse được hoặc mất precision |
| Nullability | Optional thành required | Record cũ thiếu giá trị |
| Enum change | Thêm trạng thái mới | Consumer cũ không xử lý giá trị lạ |
| Restructure | Tách address thành record | Cần transform và sửa query |
| Semantic change | total chuyển từ gross sang net | Kiểu không đổi nhưng ý nghĩa thay đổi |

### 3.1. Additive change

Thêm field optional thường dễ triển khai hơn nếu consumer cũ bỏ qua field không biết. Nhưng vẫn cần xem serializer có từ chối field dư hay không và database có default phù hợp không.

### 3.2. Rename

Rename thường được xem như xóa field cũ và thêm field mới. Cần mapping trong giai đoạn chuyển tiếp để producer và consumer có thể nâng cấp khác thời điểm.

### 3.3. Removal

Chỉ xóa field sau khi không còn producer, consumer, query, report hoặc workflow nào sử dụng. Cần quan sát mức sử dụng trước khi xóa.

### 3.4. Type change

Type change có thể làm mất thông tin. Ví dụ Decimal thành Integer cần quy tắc rounding hoặc từ chối giá trị có phần thập phân. Không được chọn quy tắc ngầm.

### 3.5. Nullability change

Optional thành required cần backfill dữ liệu cũ và đảm bảo mọi writer mới luôn cung cấp giá trị trước khi bật constraint.

### 3.6. Enum evolution

Consumer nên có hành vi rõ với enum value chưa biết: từ chối, giữ raw value, dùng fallback hoặc chuyển sang trạng thái xử lý thủ công. Không nên giả định enum chỉ có các giá trị từng biết lúc compile.

### 3.7. Semantic change

Thay đổi ý nghĩa field là rủi ro lớn dù tên và kiểu không đổi. Nếu total trước đây là gross và nay là net, nên cân nhắc field mới hoặc version mới thay vì đổi ý nghĩa âm thầm.

## 4. Versioning schema

Versioning giúp producer và consumer biết họ đang nói cùng một hợp đồng nào.

### 4.1. Version tường minh

Có thể gắn version vào định nghĩa:

~~~text
schema Order version 2 {
  id: OrderId
  customerId: CustomerId
  total: Decimal
  currency: CurrencyCode
}
~~~

Version có thể là số nguyên tăng dần, semantic version hoặc identifier bất biến tùy hệ thống.

### 4.2. Immutable schema version

Một schema version đã phát hành nên được xem là bất biến. Nếu cần thay đổi, tạo version mới. Sửa nội dung của version cũ làm artifact cũ có thể được diễn giải khác khi build lại.

### 4.3. Schema registry

Registry lưu:
- Schema ID.
- Version.
- Nội dung schema.
- Owner.
- Trạng thái phát hành.
- Compatibility policy.
- Dependency.
- Thời điểm phát hành.
- Migration path.
- Checksum hoặc signature nếu cần.

### 4.4. Version theo major/minor

Một quy ước phổ biến:
- Major: thay đổi có thể phá vỡ tương thích.
- Minor: mở rộng tương thích theo policy.
- Patch: sửa metadata hoặc mô tả mà không đổi contract.

Quy ước cần được định nghĩa cụ thể. Không phải mọi additive change đều an toàn với mọi serializer.

### 4.5. Version trong artifact

Artifact DSL nên ghi schema version và compiler version mà nó phụ thuộc. Khi runtime khởi chạy, nó có thể kiểm tra schema tương thích trước khi xử lý.

### 4.6. Versioning không thay migration

Version number cho biết khác biệt, nhưng không nói dữ liệu cần chuyển đổi ra sao. Cần migration definition hoặc transformation code tương ứng.

## 5. Backward compatibility và forward compatibility

Compatibility mô tả khả năng các phiên bản khác nhau cùng trao đổi dữ liệu.

### 5.1. Backward compatibility

Schema mới có thể đọc dữ liệu được tạo theo schema cũ. Ví dụ, phiên bản mới thêm field optional và chấp nhận record cũ thiếu field đó.

### 5.2. Forward compatibility

Consumer cũ có thể xử lý dữ liệu do producer mới tạo. Điều này thường yêu cầu consumer bỏ qua field không biết và xử lý enum hoặc tag chưa biết theo quy tắc an toàn.

### 5.3. Full compatibility

Một số hệ thống dùng thuật ngữ full compatibility khi cả backward và forward đều được duy trì theo policy xác định.

### 5.4. Compatibility không chỉ dựa trên cấu trúc

Hai schema có cùng field nhưng khác semantics vẫn không tương thích về nghiệp vụ. Ví dụ amount chuyển từ USD sang VND mà vẫn là Decimal là thay đổi nghiêm trọng.

### 5.5. Compatibility matrix

| Producer | Consumer | Câu hỏi |
| --- | --- | --- |
| v1 | v1 | Cặp hiện tại có hoạt động? |
| v1 | v2 | Consumer mới đọc dữ liệu cũ? |
| v2 | v1 | Consumer cũ đọc dữ liệu mới? |
| v2 | v2 | Cặp mới hoạt động? |

Cần test các cặp có thể cùng tồn tại trong quá trình rollout.

### 5.6. Unknown field và unknown enum

Serializer có thể bỏ qua field lạ, nhưng enum lạ thường cần policy riêng. Nếu consumer deserialize enum thành closed enum và thất bại, additive enum change có thể phá vỡ consumer cũ.

## 6. Migration plan

Một migration plan xác định các bước chuyển đổi và điều kiện hoàn tất.

### 6.1. Xác định source và target

Ghi rõ schema nguồn, schema đích, phạm vi dữ liệu và các component đang dùng version cũ.

### 6.2. Inventory dependency

Tìm:
- DSL module.
- Query.
- API producer/consumer.
- Event handler.
- Workflow definition.
- Report.
- Data export.
- Cache.
- External integration.
- Historical artifact.

Không bỏ qua consumer ít chạy hoặc job theo lịch.

### 6.3. Định nghĩa transformation

Mỗi thay đổi cần mapping:
- Field nguồn.
- Field đích.
- Conversion.
- Default.
- Null handling.
- Validation.
- Error policy.
- Data loss policy.

### 6.4. Xác định rollout sequence

Ví dụ:
1. Phát hành consumer đọc được cả schema cũ và mới.
2. Thêm field mới vào storage.
3. Cập nhật producer ghi field mới.
4. Backfill dữ liệu cũ.
5. Kiểm tra dữ liệu đã chuyển.
6. Chuyển consumer sang field mới.
7. Ngừng ghi field cũ.
8. Xóa field cũ sau thời gian quan sát.

### 6.5. Xác định success criteria

Migration chỉ hoàn tất khi:
- Tất cả record trong scope đã xử lý.
- Không còn lỗi chưa giải quyết.
- Invariant mới được thỏa.
- Consumer tương thích.
- Không còn read/write vào field cũ.
- Dashboard và audit xác nhận trạng thái.
- Rollback window hoặc kế hoạch phục hồi đã được quyết định.

### 6.6. Estimate thời gian và tài nguyên

Backfill hàng triệu record có thể ảnh hưởng production. Chia batch, giới hạn tốc độ và đo thời gian dự kiến. Cần tính cả index rebuild, lock, replication lag và storage growth.

## 7. Expand-and-contract migration

Expand-and-contract là chiến lược triển khai thay đổi không tương thích qua nhiều bước nhỏ.

Giả sử field customerCode cần đổi thành customerId.

### 7.1. Expand

Thêm customerId nhưng vẫn giữ customerCode. Schema và consumer mới có thể đọc cả hai.

~~~text
record Order {
  customerCode: String?
  customerId: CustomerId?
}
~~~

### 7.2. Dual write hoặc compatibility write

Producer mới có thể ghi cả hai field trong giai đoạn chuyển tiếp. Cần đảm bảo hai giá trị nhất quán và xác định field nào là nguồn sự thật.

### 7.3. Backfill

Chuyển dữ liệu cũ:

~~~text
customerId = resolveCustomerId(customerCode)
~~~

Backfill cần idempotent, có checkpoint và báo cáo record không chuyển được.

### 7.4. Switch reads

Consumer chuyển sang đọc customerId. Trong giai đoạn này có thể fallback sang customerCode, nhưng cần đo số lần fallback để biết khi nào dữ liệu cũ đã được xử lý hết.

### 7.5. Stop old writes

Khi mọi producer đã ghi field mới, dừng ghi customerCode. Xác nhận không còn consumer nào phụ thuộc field cũ.

### 7.6. Contract

Xóa customerCode và mọi compatibility code sau khi thời gian quan sát và rollback window kết thúc.

~~~text
Old schema
    |
    v
Expand: add new field
    |
    v
Dual-compatible application
    |
    v
Backfill old records
    |
    v
Switch reads to new field
    |
    v
Stop old writes
    |
    v
Contract: remove old field
~~~

### 7.7. Lợi ích và chi phí

Chiến lược này giảm thời gian phải triển khai đồng bộ mọi component. Đổi lại, schema và application tạm thời phức tạp hơn, cần theo dõi dual write và fallback.

## 8. Chuyển đổi dữ liệu

Migration dữ liệu biến record từ representation cũ sang representation mới.

### 8.1. Mapping đơn giản

Schema v1:

~~~text
record CustomerV1 {
  id: String
  fullName: String
}
~~~

Schema v2:

~~~text
record CustomerV2 {
  id: CustomerId
  givenName: String
  familyName: String?
}
~~~

Migration:

~~~text
migration customer_1_to_2 {
  from CustomerV1
  to CustomerV2

  transform old => {
    id: parseCustomerId(old.id),
    givenName: firstNamePart(old.fullName),
    familyName: remainingNamePart(old.fullName)
  }
}
~~~

Việc tách tên có thể không chính xác với mọi văn hóa hoặc dữ liệu cũ. Cần quy tắc cho tên một từ, khoảng trắng, danh xưng và dữ liệu bất thường. Có thể giữ legacyFullName trong giai đoạn chuyển tiếp.

### 8.2. Type conversion

Một migration chuyển String sang Integer cần:
- Trim.
- Parse.
- Kiểm tra range.
- Xử lý chuỗi rỗng.
- Xử lý ký tự không hợp lệ.
- Ghi diagnostic theo record.

Không nên thay dữ liệu không hợp lệ bằng 0 nếu 0 có ý nghĩa nghiệp vụ.

### 8.3. Default value

Default cần phân biệt:
- Giá trị mặc định nghiệp vụ.
- Giá trị tạm để backfill.
- Giá trị null có nghĩa chưa biết.
- Giá trị được suy ra từ dữ liệu khác.

Không dùng một default tùy tiện để làm migration chạy qua.

### 8.4. Unit conversion

Nếu field đổi đơn vị, migration phải chuyển giá trị theo hệ số và rounding policy. Ví dụ centimet sang meter cần quy định precision. Đơn vị nên được biểu diễn rõ trong schema hoặc type.

### 8.5. Split và merge

Tách một field thành nhiều field hoặc gộp nhiều field cần xác định thông tin có bị mất không. Nếu transformation không đảo ngược, cần lưu dữ liệu gốc trong thời gian phù hợp.

### 8.6. Reference migration

Nếu ID được đổi representation hoặc namespace, cần map foreign key và kiểm tra mọi reference. Thứ tự migration có thể phải chuyển parent trước child hoặc dùng deferred constraint.

### 8.7. Diagnostic và rejected record

Record không chuyển được nên được ghi vào báo cáo hoặc quarantine store với reason code, source ID và migration version. Không bỏ qua im lặng.

## 9. Migration DSL

Một DSL có thể khai báo migration để chuẩn hóa cách mô tả thay đổi schema.

### 9.1. Khai báo version

~~~text
schema Customer version 1 {
  id: String
  fullName: String
  email: String?
}

schema Customer version 2 {
  id: CustomerId
  givenName: String
  familyName: String?
  email: Email?
}
~~~

### 9.2. Migration definition

~~~text
migration Customer_1_to_2 {
  from Customer@1
  to Customer@2

  map id using parseCustomerId
  map fullName using splitPersonName
  rename email -> email

  validate target
}
~~~

Cú pháp là minh họa. DSL thực tế cần chỉ rõ cách map fullName khi không thể tách chính xác.

### 9.3. Migration function

Một migration có thể dùng function thuần để chuyển đổi một record. Function nên deterministic để cùng input tạo cùng output.

### 9.4. Migration metadata

Có thể khai báo:
- Migration ID.
- Source và target version.
- Owner.
- Preconditions.
- Batch size.
- Timeout.
- Retry policy.
- Validation rule.
- Rollback strategy.
- Required approval.

### 9.5. Migration graph

Khi có nhiều version, migration có thể tạo thành graph:

~~~text
v1 ---> v2 ---> v3
         \
          ---> v2.1 ---> v3
~~~

Không phải mọi đường đều cần được hỗ trợ. Cần chọn đường upgrade được công bố và tránh nhiều migration path không rõ thứ tự.

### 9.6. Direct migration và sequential migration

Có thể chuyển v1 trực tiếp sang v3 hoặc đi qua v2. Direct migration nhanh hơn khi có transformation rõ; sequential migration tái sử dụng bước đã có nhưng cần giữ các migration trung gian.

### 9.7. Static validation

Compiler hoặc migration planner có thể kiểm tra:
- Source schema tồn tại.
- Target schema tồn tại.
- Field mapping hợp lệ.
- Kiểu tương thích.
- Required field được tạo.
- Không có mapping mơ hồ.
- Migration path không có cycle.
- Function transformation được phép.

## 10. Migration có tính idempotent và resumable

Migration dữ liệu lớn có thể bị gián đoạn. Cần thiết kế để chạy lại hoặc tiếp tục an toàn.

### 10.1. Idempotency

Một migration idempotent có thể chạy lại mà không làm thay đổi kết quả thêm lần nữa. Ví dụ, chỉ set customerId nếu nó chưa được xác định và giá trị nguồn chưa thay đổi.

### 10.2. Checkpoint

Lưu tiến độ theo batch, partition hoặc key range. Khi worker restart, tiếp tục từ checkpoint đã commit.

### 10.3. Batch processing

Chia dữ liệu thành batch có kích thước hợp lý:
- Giảm transaction dài.
- Hạn chế lock.
- Dễ retry.
- Kiểm soát memory.
- Theo dõi progress.

### 10.4. Exactly-once không nên được giả định

Worker có thể crash sau khi commit dữ liệu nhưng trước khi ghi checkpoint. Batch kế tiếp có thể chạy lại. Idempotency hoặc transaction gộp data update và progress record giúp xử lý tình huống này.

### 10.5. Concurrency

Nhiều worker có thể xử lý partition khác nhau. Cần tránh hai worker cập nhật cùng record hoặc ghi checkpoint không đúng thứ tự.

### 10.6. Rate limit

Backfill có thể cạnh tranh tài nguyên với workload production. Giới hạn batch rate, CPU và database write để giữ hệ thống ổn định.

## 11. Transaction, consistency và locking

Migration thường chạm nhiều record hoặc nhiều bảng. Cần chọn consistency model phù hợp.

### 11.1. Atomic migration nhỏ

Một migration nhỏ có thể chạy trong transaction đơn. Nếu lỗi, rollback transaction.

### 11.2. Migration lớn

Không nên giữ transaction hàng giờ cho hàng triệu record. Có thể dùng batch transaction và checkpoint. Khi đó trạng thái trung gian phải được hỗ trợ bởi application.

### 11.3. Consistency invariant

Ví dụ, sau migration:
- customerId phải tham chiếu customer tồn tại.
- currency phải thuộc danh sách được hỗ trợ.
- quantity phải dương.
- Required field không null.
- Foreign key không orphan.

### 11.4. Locking

DDL hoặc backfill có thể lock table. Cần biết lock mode, thời gian lock và ảnh hưởng tới read/write traffic. Có thể dùng online schema change nếu database hỗ trợ.

### 11.5. Dual write consistency

Nếu ứng dụng ghi cả field cũ và mới, hai giá trị cần được cập nhật atomic hoặc có cơ chế reconcile. Nếu một field ghi thành công còn field kia thất bại, dữ liệu có thể lệch.

### 11.6. Eventual consistency

Trong migration phân tán, các service có thể cập nhật theo thời gian. Cần xác định khoảng thời gian chấp nhận trạng thái chưa đồng bộ và cách đọc dữ liệu trong thời gian đó.

## 12. Rollback và forward recovery

Rollback là đưa hệ thống trở lại trạng thái trước migration. Không phải migration nào cũng có thể đảo ngược hoàn toàn.

### 12.1. Reversible migration

Một migration có thể đảo ngược nếu dữ liệu gốc được giữ và transformation có inverse chính xác.

Ví dụ thêm field optional thường dễ rollback hơn xóa field và mất dữ liệu.

### 12.2. Irreversible migration

Nếu gộp hai field hoặc làm tròn số, thông tin có thể mất. Down migration không thể khôi phục dữ liệu gốc chính xác.

### 12.3. Backup và snapshot

Trước migration rủi ro cao, cần backup hoặc snapshot phù hợp. Kiểm tra khả năng restore, không chỉ xác nhận job backup đã chạy.

### 12.4. Forward recovery

Khi không thể rollback, có thể sửa migration và tiếp tục tiến về target state. Cần giữ dữ liệu lỗi, migration log và version đã commit để tránh xử lý nhầm.

### 12.5. Rollback application và rollback data

Có thể rollback application nhưng schema đã mở rộng vẫn còn. Expand-and-contract cho phép code cũ tiếp tục hoạt động trong một khoảng thời gian nếu compatibility được thiết kế trước.

### 12.6. Decision point

Trước khi chạy, xác định điều kiện:
- Tự retry.
- Dừng và giữ trạng thái.
- Rollback batch.
- Restore snapshot.
- Chuyển sang forward fix.
- Manual intervention.

## 13. Migration database và schema DSL

DSL có thể mô tả domain schema rồi sinh DDL hoặc migration script cho database.

### 13.1. Add column

~~~sql
ALTER TABLE orders
ADD COLUMN currency_code VARCHAR(3);
~~~

Thêm column có thể an toàn nếu nullable hoặc có default phù hợp, nhưng tác động phụ thuộc database và kích thước bảng.

### 13.2. Backfill

~~~sql
UPDATE orders
SET currency_code = 'VND'
WHERE currency_code IS NULL;
~~~

Ví dụ này chỉ đúng nếu mọi record cũ thực sự dùng VND. Nếu currency khác nhau, cần suy ra từ dữ liệu nguồn đáng tin cậy.

### 13.3. Add constraint

~~~sql
ALTER TABLE orders
ALTER COLUMN currency_code SET NOT NULL;
~~~

Chỉ bật constraint sau khi dữ liệu đã được kiểm tra và mọi writer cung cấp giá trị.

### 13.4. Index migration

Tạo index có thể ảnh hưởng write throughput và lock. Một số database hỗ trợ tạo index online hoặc concurrently. Cần dùng cú pháp đúng engine và theo dõi progress.

### 13.5. Rename column

Không nên rename ngay nếu ứng dụng cũ vẫn chạy. Có thể thêm column mới, dual write, backfill, switch read rồi xóa column cũ.

### 13.6. Generated migration review

Migration generator nên tạo script có thể review, diff và chạy trong môi trường staging. Không nên tự động publish DDL production chỉ dựa vào việc compile schema thành công.

## 14. Migration API và event schema

Schema API và event có nhiều producer/consumer triển khai độc lập. Compatibility là yếu tố trung tâm.

### 14.1. API request/response

Khi thêm field request, xác định server cũ có bỏ qua field không. Khi thêm field response, xác định client cũ có từ chối field dư không.

### 14.2. Event schema

Event thường được lưu lâu trong broker hoặc event store. Consumer mới có thể phải đọc event cũ trong nhiều tháng.

### 14.3. Schema registry policy

Registry có thể kiểm tra backward, forward hoặc full compatibility trước khi cho phép publish version mới.

### 14.4. Event upcasting

Một consumer có thể chuyển event cũ thành representation nội bộ mới trước khi xử lý. Upcaster nên deterministic, có version và test với event fixture lịch sử.

### 14.5. Unknown event type

Consumer cần policy khi nhận event type chưa biết: bỏ qua có kiểm soát, lưu lại, dead-letter hoặc báo lỗi. Không nên crash toàn bộ consumer nếu protocol cho phép mở rộng.

### 14.6. Dual publishing

Có thể publish event v1 và v2 trong giai đoạn chuyển tiếp, nhưng cần tránh consumer xử lý cả hai và tạo side effect hai lần. Correlation hoặc logical event identity giúp deduplicate.

### 14.7. Event semantics

Đổi tên field có thể dễ xử lý hơn đổi ý nghĩa event. Nếu OrderPaid trước đây nghĩa là đã capture và nay nghĩa là đã settle, nên tạo event mới hoặc version mới với semantics rõ.

## 15. Migration workflow context và DSL definition

Workflow dài hạn có thể tồn tại lâu hơn một lần deploy. Instance đang chạy có thể giữ context theo schema cũ.

### 15.1. Pin definition version

Mỗi instance có thể gắn với workflow definition version đã tạo nó. Điều này giúp runtime diễn giải state và context nhất quán.

### 15.2. Context migration

Khi cần chuyển instance sang definition mới, migration phải xử lý:
- Current state.
- Context fields.
- Timer.
- Pending event.
- Child workflow.
- Retry metadata.
- Compensation status.

### 15.3. State mapping

Nếu state WAITING_PAYMENT đổi thành PAYMENT_PENDING, cần mapping state và kiểm tra transition tiếp theo vẫn hợp lệ.

### 15.4. Active instance strategy

Có thể:
- Giữ instance cũ chạy đến khi kết thúc.
- Migrate instance đang chờ tại checkpoint an toàn.
- Migrate theo batch.
- Chỉ áp dụng definition mới cho instance mới.

Lựa chọn phụ thuộc khả năng tương thích runtime và thời gian sống của workflow.

### 15.5. Timer và event đang chờ

Timer đã lên lịch theo definition cũ có thể cần được giữ, hủy hoặc tạo lại. Event đang chờ cần được route đúng instance sau migration.

### 15.6. Test migration instance

Tạo fixture instance ở từng state quan trọng, migrate và xác minh context, state, timer, event subscription và kết quả tiếp tục.

## 16. Validation và kiểm tra sau migration

Migration hoàn tất về mặt kỹ thuật chưa có nghĩa dữ liệu đã đúng.

### 16.1. Precondition

Trước khi chạy:
- Kiểm tra source version.
- Kiểm tra backup.
- Kiểm tra dependency.
- Kiểm tra quyền.
- Kiểm tra disk space.
- Kiểm tra lock và maintenance window.
- Kiểm tra application compatibility.

### 16.2. Row count

So sánh số record trước và sau, có giải thích cho record được lọc, merge hoặc quarantine.

### 16.3. Aggregate checks

So sánh tổng tiền, số lượng, min/max và các aggregate quan trọng. Với conversion, có thể kiểm tra tổng trước/sau theo quy tắc.

### 16.4. Referential integrity

Kiểm tra foreign key, orphan record và quan hệ một-nhiều.

### 16.5. Domain invariant

Chạy validator nghiệp vụ sau migration:
- Không có amount âm.
- Required field có giá trị.
- Enum nằm trong tập hợp hợp lệ.
- State và context nhất quán.

### 16.6. Sample inspection

Kiểm tra mẫu record từ các nhóm:
- Record bình thường.
- Record null hoặc thiếu field.
- Record có giá trị biên.
- Record từng bị lỗi.
- Record được transform theo nhiều nhánh.

### 16.7. Shadow read

Trong giai đoạn chuyển tiếp, đọc cả representation cũ và mới rồi so sánh kết quả mà chưa dùng output mới để quyết định nghiệp vụ. Đây là cách phát hiện khác biệt trước khi chuyển traffic.

## 17. Testing migration

Migration cần test riêng vì nó biến đổi dữ liệu đã tồn tại.

### 17.1. Unit test transformation

Kiểm tra từng function map với input hợp lệ, null, boundary và malformed data.

### 17.2. Fixture test

Lưu fixture schema cũ đại diện cho dữ liệu thực tế đã ẩn danh. Chạy migration và so sánh expected target record.

### 17.3. Compatibility test

Test producer/consumer theo matrix giữa các version đang có thể cùng chạy.

### 17.4. Integration test

Chạy migration trên database thử nghiệm cùng engine/version tương đương production. Kiểm tra DDL, index, constraint và transaction behavior.

### 17.5. Idempotency test

Chạy migration hai lần và xác minh lần hai không làm sai dữ liệu hoặc tạo side effect mới.

### 17.6. Resume test

Dừng migration giữa một batch, restart và xác minh checkpoint tiếp tục đúng, không bỏ sót hoặc nhân đôi record.

### 17.7. Failure injection

Mô phỏng:
- Database connection loss.
- Lock timeout.
- Disk full.
- Invalid source record.
- Worker crash.
- Network failure.
- Constraint violation.

Kiểm tra migration dừng hoặc tiếp tục theo policy.

### 17.8. Performance test

Đo batch throughput, lock duration, replication lag, CPU, memory và thời gian hoàn tất trên dữ liệu gần quy mô thật.

### 17.9. Production rehearsal

Chạy thử trên snapshot hoặc bản sao dữ liệu đã được bảo vệ. Ghi lại thời gian, resource và số record lỗi để điều chỉnh plan.

## 18. Vận hành migration trong production

Migration production cần quy trình có thể quan sát và kiểm soát.

### 18.1. Migration ledger

Lưu migration ID, source/target version, checksum, trạng thái, start/end time, số batch, số record, lỗi và actor khởi chạy.

### 18.2. Single runner hoặc coordination

Tránh hai worker cùng chạy một migration không được thiết kế song song. Dùng lock hoặc lease có expiration và fencing token nếu cần.

### 18.3. Progress metrics

Theo dõi:
- Records scanned.
- Records migrated.
- Records rejected.
- Batch duration.
- Retry count.
- Queue lag.
- Database load.
- Estimated remaining work.

### 18.4. Pause và resume

Migration lớn nên có khả năng pause có kiểm soát. Khi resume, kiểm tra schema và migration version vẫn đúng.

### 18.5. Throttling

Giới hạn tốc độ ghi để tránh làm chậm giao dịch production. Có thể điều chỉnh batch size theo load.

### 18.6. Alert

Cảnh báo khi:
- Error rate tăng.
- Progress không thay đổi.
- Lock wait kéo dài.
- Replication lag vượt ngưỡng.
- Disk gần đầy.
- Migration chạy quá deadline.

### 18.7. Audit

Ghi ai phê duyệt, ai chạy, version nào, môi trường nào và quyết định rollback/forward fix. Không ghi dữ liệu nhạy cảm không cần thiết.

## 19. Security và data privacy

Migration thường đọc và ghi lượng lớn dữ liệu, do đó cần bảo vệ quyền và thông tin nhạy cảm.

### 19.1. Least privilege

Migration identity chỉ cần quyền đọc nguồn và ghi target trong phạm vi cần thiết. Tránh dùng administrator credential dùng chung.

### 19.2. Secret management

Credential lấy từ secret manager hoặc cơ chế được bảo vệ. Không nhúng password vào migration source, command line hoặc log.

### 19.3. Data minimization

Chỉ đưa field cần thiết vào transformation. Không dump toàn bộ record vào diagnostic.

### 19.4. Encryption

Dữ liệu nhạy cảm cần được bảo vệ khi truyền và lưu. File export, snapshot và temporary staging cũng cần cùng chính sách.

### 19.5. Retention

Bản sao dữ liệu cũ, quarantine record và backup có retention rõ. Migration có thể làm dữ liệu cá nhân tồn tại ở nhiều nơi hơn nếu không cleanup.

### 19.6. Tenant isolation

Migration theo tenant phải xác thực tenant scope ở host hoặc database boundary. Không tin tenant ID từ DSL input.

## 20. Ví dụ hoàn chỉnh: nâng Order schema từ v1 lên v2

Giả sử Order v1 lưu mã khách hàng dưới dạng String, tổng tiền chưa có currency và địa chỉ giao hàng nằm trong một field text.

### 20.1. Schema v1

~~~text
schema Order version 1 {
  id: String
  customerCode: String
  total: Decimal
  shippingAddress: String?
}
~~~

### 20.2. Schema v2

~~~text
schema Order version 2 {
  id: OrderId
  customerId: CustomerId
  total: Money
  shippingAddress: Address?
  createdAt: Instant
}
~~~

### 20.3. Transformation policy

- id: parse thành OrderId; record không parse được vào quarantine.
- customerCode: resolve thành CustomerId từ customer registry.
- total: gắn currency theo nguồn đáng tin cậy; không đoán currency nếu không xác định được.
- shippingAddress: parse theo format cũ; nếu không thể parse, giữ legacy text trong vùng compatibility hoặc quarantine theo policy.
- createdAt: suy ra từ audit timestamp nếu có; nếu không, dùng unknown representation thay vì tạo timestamp giả.

### 20.4. Expand phase

Thêm field mới nullable và cập nhật application để đọc cả schema v1 và v2. Producer bắt đầu ghi field mới khi có đủ thông tin.

### 20.5. Backfill

Chạy batch migration theo ID range. Mỗi batch ghi:
- Số record đọc.
- Số record chuyển thành công.
- Số record quarantine.
- Checkpoint.
- Duration.

### 20.6. Validation

Kiểm tra:
- Mọi customerId tham chiếu customer hợp lệ.
- Money có amount và currency.
- Address parse thành công hoặc có legacy marker.
- Record count được giải thích.
- Aggregate total theo currency khớp theo policy.

### 20.7. Switch read

Chuyển query và workflow sang customerId, Money và Address. Theo dõi fallback vào field cũ. Nếu fallback vẫn xảy ra, chưa được xóa field cũ.

### 20.8. Contract phase

Sau khi producer và consumer đã chuyển, dừng dual write, chờ rollback window, rồi xóa customerCode và legacy shippingAddress theo migration riêng.

### 20.9. Migration record

~~~text
MigrationRun {
  id: "order-v1-v2"
  fromVersion: 1
  toVersion: 2
  status: COMPLETED
  scanned: 1200000
  migrated: 1198500
  quarantined: 1500
}
~~~

Các số liệu chỉ minh họa. Quarantine record cần được xử lý theo quy trình riêng trước khi tuyên bố dữ liệu hoàn toàn sạch.

## 21. Những lỗi thường gặp khi di trú schema

**Đổi schema và deploy mọi component cùng lúc.** Các service có thể cập nhật không đồng bộ. Hãy dùng compatibility window và rollout theo giai đoạn.

**Xóa field cũ quá sớm.** Consumer hoặc workflow cũ vẫn có thể cần field đó. Hãy đo mức sử dụng và chỉ contract sau khi xác nhận.

**Đổi kiểu mà không định nghĩa conversion.** Dữ liệu có thể mất precision hoặc parse thất bại. Hãy nêu rõ rounding, null và malformed data policy.

**Thêm required field mà không backfill.** Record cũ không thỏa constraint. Hãy thêm nullable, backfill và chỉ sau đó bật required constraint.

**Dùng default giả.** Giá trị mặc định có thể làm dữ liệu sai nhưng trông hợp lệ. Hãy phân biệt unknown với default nghiệp vụ.

**Migration không idempotent.** Retry có thể nhân đôi hoặc biến đổi dữ liệu nhiều lần. Hãy dùng stable key và checkpoint.

**Một transaction quá lớn.** Lock kéo dài và rollback tốn kém. Hãy chia batch nếu migration có thể được thiết kế an toàn ở trạng thái trung gian.

**Không kiểm tra semantics.** Cùng type nhưng khác ý nghĩa có thể tạo kết quả sai. Hãy version hoặc đổi tên field khi meaning thay đổi.

**Không test consumer cũ.** Enum mới hoặc field mới có thể làm client cũ crash. Hãy kiểm tra compatibility matrix.

**Không giữ lịch sử migration.** Khó biết version nào đã chạy và ai đã thực hiện. Hãy dùng migration ledger và checksum.

**Giả định rollback luôn khả thi.** Transformation có thể mất dữ liệu. Hãy xác định forward recovery và backup trước khi chạy.

**Bỏ qua workflow đang chạy.** Context cũ có thể không đọc được bởi definition mới. Hãy pin version hoặc migrate instance có kiểm soát.

**Không kiểm tra dữ liệu sau migration.** Job hoàn tất không chứng minh dữ liệu đúng. Hãy kiểm tra count, aggregate, reference và domain invariant.

## 22. Quy trình xây dựng và triển khai schema migration

Có thể áp dụng trình tự sau:

1. **Inventory:** tìm tất cả schema, producer, consumer và artifact phụ thuộc.
2. **Version:** tạo schema version mới bất biến và xác định compatibility policy.
3. **Classify:** phân loại additive, breaking, type, nullability và semantic change.
4. **Design:** mô tả transformation, default, error handling và data loss policy.
5. **Plan:** chọn expand-and-contract, sequential hoặc direct migration.
6. **Validate statically:** kiểm tra mapping, type, required field và dependency graph.
7. **Test:** chạy fixture, compatibility, idempotency, resume và failure injection.
8. **Rehearse:** chạy trên snapshot hoặc staging với quy mô đại diện.
9. **Deploy expand:** phát hành schema và application tương thích.
10. **Backfill:** chuyển dữ liệu theo batch, checkpoint và throttle.
11. **Verify:** kiểm tra invariant, count, aggregate và consumer behavior.
12. **Switch:** chuyển read/write sang schema mới.
13. **Contract:** loại bỏ field cũ sau thời gian quan sát.
14. **Record:** lưu migration ledger, metrics và audit.

## 23. Kết luận

Di trú schema là quá trình thay đổi hợp đồng dữ liệu và chuyển các thành phần phụ thuộc sang phiên bản mới. Với DSL, schema có thể xuất hiện trong domain model, query, API, event, database, artifact và workflow context. Một thay đổi nhỏ như rename field có thể ảnh hưởng nhiều producer, consumer và instance đang chạy.

Một chiến lược an toàn cần versioning bất biến, compatibility policy, inventory dependency, transformation tường minh, migration có thể quan sát và validation sau chuyển đổi. Expand-and-contract giúp triển khai dần khi phiên bản cũ và mới cùng tồn tại. Migration lớn cần batch, checkpoint, idempotency, throttling và recovery plan. Workflow dài hạn cần pin definition hoặc chuyển state và context theo mapping được kiểm thử.

Hãy xem migration là một thay đổi có vòng đời, có trạng thái và có trách nhiệm dữ liệu. Khi biết rõ dữ liệu đến từ đâu, được chuyển đổi thế nào, ai đang sử dụng schema nào và điều kiện nào cho phép loại bỏ phiên bản cũ, hệ thống DSL có thể tiến hóa mà vẫn duy trì tính nhất quán, khả năng tương thích và độ tin cậy.

