# Kiểm tra toàn vẹn

## 1. Kiểm tra toàn vẹn trong lưu trữ và trao đổi DSL

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường tạo ra nhiều loại artifact: tệp nguồn, cấu hình đã chuẩn hóa, schema, module, mã trung gian, bytecode, execution plan và dữ liệu đầu vào. Các artifact này có thể được lưu trên đĩa, đưa vào kho phiên bản, đóng gói, truyền qua mạng hoặc chuyển giữa các dịch vụ.

Trong suốt quá trình đó, dữ liệu có thể bị hỏng, bị cắt cụt, bị thay đổi ngoài ý muốn hoặc bị thay thế bởi một phiên bản không mong đợi. **Kiểm tra toàn vẹn (integrity checking)** là việc xác nhận dữ liệu vẫn giữ nguyên nội dung và cấu trúc cần thiết so với trạng thái tham chiếu hoặc quy tắc đã xác định.

Ví dụ, một pipeline DSL được biên dịch thành artifact:

~~~text
orders.dsl
    |
    v
compiler
    |
    v
orders.plan
    |
    v
package
    |
    v
artifact repository
    |
    v
deployment service
~~~

Kiểm tra toàn vẹn có thể được thực hiện sau khi compiler ghi orders.plan, khi package được tải lên repository, sau khi deployment service tải xuống và trước khi runtime nạp artifact. Mỗi bước xác nhận dữ liệu nhận được khớp với dữ liệu đã được tạo hoặc công bố.

Kiểm tra toàn vẹn giúp phát hiện:

- Nội dung bị thay đổi do lỗi ghi hoặc đọc.
- Tệp truyền qua mạng bị hỏng hoặc thiếu byte.
- Artifact bị cắt cụt hoặc ghép sai thứ tự.
- Một phần package không khớp với manifest.
- Cache trả về dữ liệu không tương ứng với khóa hoặc phiên bản.
- Schema hoặc metadata không còn khớp với artifact.
- Nội dung bị sửa đổi sau khi đã được ký hoặc công bố, nếu có cơ chế xác thực phù hợp.

Toàn vẹn là một thuộc tính quan trọng của lưu trữ và trao đổi, nhưng không tự bảo đảm dữ liệu bí mật, luôn sẵn sàng hoặc có ý nghĩa đúng về mặt nghiệp vụ. Một tệp có checksum hợp lệ vẫn có thể chứa cấu hình sai hoặc mã độc nếu nội dung đó đã sai ngay từ đầu.

## 2. Các khái niệm cần phân biệt

Khi thiết kế cơ chế bảo vệ artifact DSL, cần phân biệt một số mục tiêu:

- **Integrity:** dữ liệu không bị thay đổi ngoài ý muốn hoặc thay đổi trái phép mà không bị phát hiện.
- **Authenticity:** xác nhận dữ liệu thực sự đến từ nguồn hoặc chủ thể được tin cậy.
- **Confidentiality:** ngăn người không có quyền đọc nội dung.
- **Availability:** bảo đảm dữ liệu có thể được truy cập khi cần.
- **Consistency:** các bản sao hoặc phần dữ liệu tuân theo cùng một trạng thái hoặc quy tắc.
- **Validity:** dữ liệu đúng định dạng và đáp ứng schema hoặc quy tắc ngữ nghĩa.

Các thuộc tính này có liên hệ nhưng không thay thế nhau.

Ví dụ, một package có SHA-256 khớp với digest trong manifest có thể được xác nhận là giống nội dung mà manifest mô tả. Tuy nhiên, nếu attacker có thể sửa cả package lẫn manifest, việc so sánh đó không xác nhận nguồn phát hành. Cần chữ ký số hoặc MAC để xác thực manifest.

| Cơ chế | Phát hiện lỗi ngẫu nhiên | Phát hiện sửa đổi có chủ ý | Xác thực nguồn |
|---|---:|---:|---:|
| Kích thước tệp | Hạn chế | Không | Không |
| Checksum đơn giản | Có | Không đáng tin cậy | Không |
| CRC | Có, đặc biệt lỗi truyền | Không | Không |
| Hash mật mã | Có | Chỉ khi digest được bảo vệ | Không tự nó |
| HMAC | Có | Có nếu khóa bí mật được giữ an toàn | Xác thực bên biết khóa |
| Chữ ký số | Có | Có nếu khóa công khai được tin cậy | Có, theo danh tính khóa ký |

## 3. Mô hình lỗi và ranh giới tin cậy

Trước khi chọn thuật toán, cần xác định dữ liệu có thể bị thay đổi ở đâu và ai có thể tác động đến nó.

### 3.1. Lỗi ngẫu nhiên

Lỗi ngẫu nhiên có thể đến từ:

- Thiết bị lưu trữ hoặc bộ nhớ gặp lỗi.
- Tiến trình bị dừng giữa lúc ghi tệp.
- Truyền dữ liệu bị mất hoặc hỏng.
- Lỗi phần mềm trong serialization hoặc deserialization.
- Ghép chunk sai thứ tự.
- Cache hoặc replica trả về phiên bản cũ.
- Tệp bị cắt cụt do giới hạn dung lượng.

Checksum hoặc hash thường đủ để phát hiện nhiều lỗi loại này, miễn là giá trị tham chiếu được lưu độc lập và đáng tin cậy.

### 3.2. Thay đổi có chủ ý

Một người hoặc tiến trình không đáng tin cậy có thể sửa artifact, manifest hoặc metadata. Nếu attacker có quyền thay đổi cả nội dung lẫn digest, checksum thông thường không đủ.

Để chống giả mạo, cần xác thực bằng MAC hoặc chữ ký số, đồng thời bảo vệ khóa và kênh phân phối khóa công khai.

### 3.3. Ranh giới tin cậy

Hãy xác định:

- Ai tạo artifact?
- Ai tính digest?
- Digest được lưu ở đâu?
- Ai có quyền sửa manifest?
- Ai ký package?
- Runtime tin cậy khóa nào?
- Artifact được truyền qua bao nhiêu hệ thống?
- Cache và replica có thể bị sửa độc lập không?

Một digest chỉ có ý nghĩa nếu bên kiểm tra có thể tin cậy giá trị tham chiếu. Nếu không, kẻ tấn công có thể thay cả hai phía.

## 4. Checksum và hash

Checksum và hash đều tạo ra một giá trị tóm tắt từ dữ liệu đầu vào. Tuy nhiên, chúng được thiết kế cho các mục tiêu khác nhau.

### 4.1. Checksum

Checksum thường được thiết kế để phát hiện lỗi truyền hoặc lỗi lưu trữ ngẫu nhiên với chi phí thấp. Một số checksum có thể phát hiện tốt các mẫu lỗi như bit flip hoặc burst error.

Ví dụ:

- XOR checksum.
- Adler-32.
- CRC-32.
- CRC-32C.

Checksum không phải cơ chế xác thực mật mã. Attacker có thể sửa dữ liệu và tính lại checksum tương ứng.

### 4.2. CRC

CRC (Cyclic Redundancy Check) xem dữ liệu như một đa thức trên trường nhị phân và tính phần dư theo một đa thức sinh đã chọn. CRC thường được dùng trong giao thức truyền, thiết bị lưu trữ và định dạng tệp.

CRC phù hợp để phát hiện nhiều lỗi truyền ngẫu nhiên, đặc biệt các chuỗi lỗi ngắn theo đặc tính của đa thức. Nó không được thiết kế để chống kẻ tấn công có khả năng chủ động sửa dữ liệu.

### 4.3. Hash mật mã

Hash mật mã ánh xạ dữ liệu có độ dài bất kỳ thành digest có độ dài cố định. Một thuật toán an toàn cần có các tính chất như:

- Khó tìm hai đầu vào khác nhau có cùng digest (collision resistance).
- Khó tìm đầu vào thứ hai có cùng digest với một đầu vào đã cho (second-preimage resistance).
- Khó khôi phục đầu vào từ digest (preimage resistance).

Các thuật toán thường gặp:

- SHA-256.
- SHA-384.
- SHA-512.
- SHA-3.

Không nên dùng MD5 hoặc SHA-1 cho mục tiêu chống giả mạo mới vì các thuật toán này có điểm yếu collision đã biết. Khi chọn thuật toán, cần theo chính sách bảo mật và yêu cầu tương thích của hệ thống.

### 4.4. Digest không phải encryption

Hash là hàm một chiều, không phải mã hóa có khóa để khôi phục dữ liệu. Nếu cần giữ bí mật nội dung, dùng encryption phù hợp. Nếu cần kiểm tra nội dung không bị thay đổi, dùng hash được bảo vệ hoặc cơ chế xác thực mật mã.

## 5. Kiểm tra bằng kích thước và metadata

Trước khi tính hash, hệ thống thường kiểm tra một số thuộc tính cơ bản:

- Kích thước tệp.
- Loại artifact.
- Phiên bản định dạng.
- Số lượng record hoặc chunk.
- Tên và đường dẫn logic.
- Thời điểm tạo hoặc phiên bản nguồn.

Kích thước giúp phát hiện tệp bị cắt cụt hoặc có độ dài không mong đợi. Tuy nhiên, hai nội dung khác nhau có thể có cùng kích thước, nên size không thay thế checksum hoặc hash.

Metadata cũng cần được bảo vệ nếu nó ảnh hưởng cách diễn giải artifact. Ví dụ, cùng một byte sequence có thể được diễn giải khác nhau theo encoding, schema version hoặc compiler target.

## 6. Hash toàn bộ artifact

Với artifact nhỏ hoặc vừa, cách đơn giản là tính digest trên toàn bộ byte sequence.

Ví dụ package:

~~~text
artifact: billing.plan
algorithm: SHA-256
digest: 8b...e4
size: 18432
~~~

Khi nhận package, hệ thống đọc nội dung, tính lại SHA-256 và so sánh với digest tham chiếu. Nếu khác nhau, artifact không khớp với bản đã công bố.

### 6.1. Hash byte, không hash cách hiển thị

Hash được tính trên byte sequence. Nếu cùng một nội dung văn bản được mã hóa UTF-8 và UTF-16, byte sequence khác nhau và digest cũng khác.

Tương tự, newline LF và CRLF, thứ tự key trong JSON, khoảng trắng hoặc cách serialize số có thể làm thay đổi byte. Nếu mục tiêu là xác nhận đúng artifact đã phát hành, hash byte chính xác là phù hợp. Nếu mục tiêu là so sánh ý nghĩa logic của hai biểu diễn, cần canonicalization trước khi hash.

### 6.2. Lưu digest bên ngoài artifact

Có thể lưu digest trong manifest, metadata repository hoặc hệ thống catalog. Cần bảo vệ manifest theo cùng mức tin cậy cần thiết. Nếu digest nằm trong chính tệp mà attacker có thể sửa cùng lúc, nó không tạo ra ranh giới xác thực.

### 6.3. So sánh an toàn

Khi so sánh MAC hoặc digest trong bối cảnh bảo mật, nên dùng hàm so sánh constant-time do thư viện mật mã cung cấp thay vì tự viết vòng lặp dừng ngay tại byte khác đầu tiên. Điều này giảm nguy cơ rò rỉ thông tin qua thời gian so sánh.

## 7. Kiểm tra toàn vẹn trong serialization

DSL thường lưu cấu trúc thành JSON, YAML, protobuf, CBOR hoặc định dạng nhị phân riêng. Serialization chuyển cấu trúc dữ liệu thành byte; deserialization chuyển byte trở lại cấu trúc.

### 7.1. Kiểm tra trước và sau serialization

Một quy trình có thể gồm:

1. Xác thực cấu trúc dữ liệu trong bộ nhớ.
2. Serialize bằng định dạng và phiên bản đã chọn.
3. Tính digest trên byte đã serialize.
4. Lưu hoặc truyền byte cùng metadata tham chiếu.
5. Kiểm tra digest khi nhận.
6. Deserialize.
7. Kiểm tra schema và bất biến ngữ nghĩa sau khi đọc.

Hash xác nhận byte không đổi so với digest tham chiếu; schema validation xác nhận byte có thể được diễn giải thành cấu trúc hợp lệ. Cần cả hai nếu mục tiêu là artifact đúng định dạng và không bị thay đổi.

### 7.2. Serialization không xác định

Hai lần serialize cùng một đối tượng logic có thể tạo byte khác nhau nếu:

- Thứ tự trường hoặc key không ổn định.
- Timestamp hoặc ID được tự sinh.
- Map được duyệt theo thứ tự không xác định.
- Số thực có nhiều cách biểu diễn.
- Whitespace hoặc newline thay đổi.
- Phiên bản serializer thay đổi.

Điều này không có nghĩa hash bị lỗi. Hash đang phản ánh đúng byte khác nhau. Nếu cần digest ổn định cho cùng nội dung logic, cần canonical serialization.

### 7.3. Canonicalization

Canonicalization chuyển các biểu diễn tương đương về một dạng chuẩn trước khi tính hash. Quy tắc có thể bao gồm:

- Sắp xếp key theo thứ tự quy định.
- Chuẩn hóa encoding.
- Quy định cách biểu diễn số.
- Chuẩn hóa newline.
- Loại bỏ trường không thuộc nội dung logic.
- Quy định xử lý Unicode.
- Quy định thứ tự phần tử chỉ khi ngữ nghĩa cho phép.

Không được tùy tiện sắp xếp mọi danh sách. Nếu thứ tự phần tử mang ý nghĩa trong DSL, canonicalizer phải giữ nguyên thứ tự đó.

### 7.4. Canonical format version

Canonicalization cũng là một phần của hợp đồng. Nên ghi phiên bản canonical format để digest có thể được tái tính theo đúng quy tắc. Nếu thay đổi canonicalization mà không đổi version, cùng một artifact logic có thể cho kết quả khác mà không rõ nguyên nhân.

## 8. Manifest và kiểm tra package

Một package DSL có thể chứa nhiều tệp:

~~~text
release/
    manifest.json
    workflow.dsl
    schema.json
    modules/
        billing.dsl
        tax.dsl
    compiled/
        billing.plan
~~~

Manifest liệt kê thành phần và digest tương ứng:

~~~json
{
  "formatVersion": 1,
  "files": [
    {
      "path": "workflow.dsl",
      "size": 1204,
      "algorithm": "SHA-256",
      "digest": "..."
    },
    {
      "path": "schema.json",
      "size": 980,
      "algorithm": "SHA-256",
      "digest": "..."
    }
  ]
}
~~~

Khi kiểm tra package:

1. Đọc manifest và xác nhận format version được hỗ trợ.
2. Xác thực manifest nếu package có chữ ký hoặc MAC.
3. Kiểm tra từng đường dẫn nằm trong phạm vi package hợp lệ.
4. Kiểm tra kích thước và digest của từng tệp.
5. Phát hiện tệp thiếu, tệp thừa hoặc đường dẫn trùng theo chính sách.
6. Kiểm tra schema và quan hệ phụ thuộc giữa các artifact.
7. Chỉ đưa package vào trạng thái sẵn sàng khi mọi điều kiện bắt buộc thành công.

### 8.1. Manifest cũng cần toàn vẹn

Nếu chỉ kiểm tra các tệp theo digest trong manifest mà manifest không được xác thực, người sửa package có thể thay file và cập nhật digest. Vì vậy, cần bảo vệ manifest bằng chữ ký số, HMAC hoặc một kênh tin cậy khác khi threat model có attacker chủ động.

### 8.2. Đường dẫn package

Manifest có thể chứa đường dẫn tương đối. Khi giải nén, cần ngăn path traversal như ../ hoặc đường dẫn tuyệt đối có thể ghi ra ngoài thư mục đích. Integrity check không thay thế kiểm tra đường dẫn an toàn.

### 8.3. File không được liệt kê

Package có thể chứa tệp không có trong manifest. Chính sách nên xác định có từ chối file thừa hay không. Với artifact release có cấu trúc chặt, từ chối file không được khai báo giúp tránh nội dung ngoài dự kiến.

## 9. HMAC và xác thực thông điệp

Hash mật mã không có khóa. Bất kỳ ai sửa được dữ liệu cũng có thể tính digest mới. **HMAC (Hash-based Message Authentication Code)** kết hợp hash mật mã với khóa bí mật để xác thực tính toàn vẹn và nguồn gốc trong nhóm các bên biết khóa.

Ví dụ:

~~~text
tag = HMAC-SHA-256(secret_key, message)
~~~

Bên nhận tính lại HMAC với cùng khóa và so sánh tag. Nếu tag khớp, dữ liệu có thể được xác nhận là đã được tạo bởi một bên nắm khóa, với giả định khóa chưa bị lộ.

### 9.1. HMAC phù hợp khi nào?

- Hai dịch vụ cùng thuộc một hệ thống và chia sẻ khóa bí mật.
- Một artifact được truyền giữa các thành phần có quan hệ tin cậy.
- Cần phát hiện nội dung bị sửa bởi bên không có khóa.

### 9.2. Hạn chế của HMAC

- Mọi bên có quyền xác minh cũng có khóa tạo HMAC.
- Khó phân biệt chính xác bên nào trong nhóm đã tạo thông điệp.
- Quản lý và xoay vòng khóa cần được thiết kế.
- Nếu khóa bị lộ, attacker có thể tạo tag hợp lệ.

Nếu cần xác minh công khai hoặc chứng minh artifact do một chủ thể ký mà không trao quyền ký cho người xác minh, chữ ký số phù hợp hơn.

## 10. Chữ ký số cho artifact DSL

Chữ ký số dùng khóa riêng để ký và khóa công khai để xác minh. Người phát hành giữ private key; runtime hoặc người nhận dùng public key đã tin cậy để kiểm tra.

Quy trình khái quát:

1. Tạo package và manifest.
2. Canonicalize phần dữ liệu cần ký.
3. Tính digest hoặc dùng thuật toán chữ ký theo chuẩn.
4. Ký bằng private key.
5. Phân phối package, manifest và chữ ký.
6. Người nhận xác minh chữ ký bằng public key tin cậy.
7. Kiểm tra digest và nội dung các tệp.

### 10.1. Chữ ký chứng minh điều gì?

Chữ ký hợp lệ cho biết dữ liệu đã được ký bằng private key tương ứng với public key dùng để xác minh và nội dung được kiểm tra không khác nội dung đã ký.

Chữ ký không chứng minh:

- Nội dung là đúng về nghiệp vụ.
- Người ký có thẩm quyền phát hành nếu trust store cấu hình sai.
- Private key chưa từng bị lộ.
- Artifact không chứa lỗ hổng hoặc mã độc.
- Artifact phù hợp với mọi runtime hoặc schema.

### 10.2. Key ID và trust store

Package nên xác định key ID hoặc key reference để verifier chọn khóa công khai phù hợp. Trust store cần quản lý:

- Khóa nào được tin cậy.
- Chủ thể hoặc mục đích của khóa.
- Thời hạn hiệu lực.
- Trạng thái thu hồi.
- Chính sách thuật toán.
- Quy tắc xoay vòng.

Không nên tin cậy public key chỉ vì nó được đóng gói cạnh chữ ký. Kẻ tấn công có thể thay cả package, signature và public key.

### 10.3. Chữ ký và thời gian

Nếu cần xác nhận thời điểm ký, có thể dùng timestamping service hoặc cơ chế chứng thực thời gian phù hợp. Timestamp trong manifest do chính người phát hành ghi không tự chứng minh thời điểm thực.

### 10.4. Chữ ký trên manifest hay từng tệp?

Ký manifest có thể bảo vệ danh sách file, đường dẫn, kích thước và digest. Nhờ vậy một chữ ký có thể xác thực toàn bộ package nếu manifest bao phủ đầy đủ nội dung cần bảo vệ.

Ký từng tệp có thể hữu ích khi artifact được phân phối độc lập hoặc xác minh theo từng phần. Hệ thống cần tránh bỏ sót metadata quan trọng như tên, version, target và dependency.

## 11. Kiểm tra toàn vẹn khi truyền dữ liệu

Khi truyền artifact qua HTTP, message queue, object storage hoặc giao thức riêng, có thể kiểm tra toàn vẹn ở nhiều tầng.

### 11.1. Transport integrity

Một số giao thức truyền có cơ chế phát hiện lỗi ở tầng frame, packet hoặc record. TLS cũng cung cấp bảo vệ toàn vẹn và xác thực dữ liệu trong phiên kết nối theo bộ mã và cấu hình được dùng.

Tuy nhiên, transport integrity chỉ bảo vệ trong phạm vi kết nối hoặc giao thức tương ứng. Nó không thay thế việc kiểm tra artifact sau khi lưu vào repository, sao chép giữa hệ thống hoặc lấy từ cache.

### 11.2. Application-level digest

Ứng dụng có thể gửi digest cùng metadata:

~~~text
Content-Length: 18432
Content-Digest: sha-256=:base64-value:
~~~

Bên nhận tính digest trên đúng byte sequence được chỉ định và so sánh. Cần tuân theo quy ước của giao thức; không tự giả định header hoặc thuật toán giống nhau giữa các hệ thống.

### 11.3. End-to-end verification

Một quy trình tốt kiểm tra nội dung ở cả điểm tạo và điểm sử dụng:

~~~text
Producer
   |
   | serialize + digest
   v
Transfer
   |
   | receive + verify
   v
Storage
   |
   | read + verify
   v
Consumer / Runtime
~~~

Nếu chỉ kiểm tra ở một hop, dữ liệu vẫn có thể bị thay đổi sau hop đó. End-to-end verification xác nhận artifact đến đúng consumer với nội dung mong đợi.

### 11.4. Retry và resume

Khi truyền bị gián đoạn, client có thể tiếp tục từ offset hoặc tải lại. Cần xác minh:

- Offset bắt đầu và độ dài chunk.
- Chunk thuộc đúng artifact và phiên bản.
- Không có chunk trùng hoặc thiếu.
- Thứ tự ghép đúng.
- Digest cuối cùng của toàn bộ artifact khớp.

Không nên coi việc từng chunk có checksum hợp lệ là đủ để chứng minh toàn bộ tệp ghép đúng thứ tự.

## 12. Kiểm tra theo chunk

Với tệp lớn, có thể chia dữ liệu thành các chunk và tính digest riêng:

~~~text
artifact.bin
    |
    +-- chunk 0 -> digest 0
    +-- chunk 1 -> digest 1
    +-- chunk 2 -> digest 2
    +-- chunk 3 -> digest 3
~~~

Lợi ích:

- Phát hiện chunk bị hỏng mà không cần tải lại toàn bộ.
- Hỗ trợ truyền song song.
- Hỗ trợ resume.
- Giảm lượng dữ liệu cần đọc lại khi chỉ một phần thay đổi.

### 12.1. Chunk identity

Mỗi chunk nên gắn với:

- Artifact ID hoặc content version.
- Index hoặc byte offset.
- Kích thước dự kiến.
- Digest.
- Thuật toán digest.

Nếu chỉ lưu digest mà không có index hoặc offset đáng tin cậy, chunk có thể bị hoán đổi vị trí mà không được phát hiện khi kiểm tra riêng lẻ.

### 12.2. Kiểm tra toàn tệp

Sau khi ghép, vẫn nên tính digest toàn tệp và so sánh với digest gốc. Điều này kiểm tra cả thứ tự và việc ghép đủ chunk.

### 12.3. Kích thước chunk

Chunk nhỏ giúp retry chính xác và phân phối linh hoạt nhưng tăng metadata và số request. Chunk lớn giảm overhead nhưng truyền lại nhiều dữ liệu hơn khi lỗi. Kích thước phù hợp phụ thuộc kích thước artifact, mạng và storage.

## 13. Merkle tree

Merkle tree tổ chức digest của các phần dữ liệu thành cây. Lá chứa hash của chunk; node cha chứa hash kết hợp các hash con theo quy tắc xác định.

Ví dụ:

~~~text
                 Root Hash
                /         \
             H01           H23
            /  \          /  \
          H0    H1      H2    H3
          |     |       |     |
       Chunk0 Chunk1 Chunk2 Chunk3
~~~

Một cách xây dựng:

~~~text
H0 = SHA256(Chunk0)
H1 = SHA256(Chunk1)
H2 = SHA256(Chunk2)
H3 = SHA256(Chunk3)

H01 = SHA256(H0 || H1)
H23 = SHA256(H2 || H3)

Root = SHA256(H01 || H23)
~~~

Trong triển khai thực tế, cần domain separation hoặc cách mã hóa node/leaf rõ ràng để tránh nhập nhằng giữa hash của dữ liệu lá và hash của node nội bộ. Cũng cần quy định cách xử lý số lá lẻ.

### 13.1. Merkle proof

Để chứng minh một chunk thuộc artifact có root hash đã biết, bên nhận không cần tải toàn bộ cây. Nó có thể nhận chunk cùng các sibling hash trên đường từ lá đến root. Verifier tính lại các node trên đường và so sánh root.

### 13.2. Ứng dụng

Merkle tree hữu ích khi:

- Artifact rất lớn.
- Chỉ cần tải hoặc xác minh một phần.
- Có nhiều replica hoặc node phân phối.
- Muốn phát hiện chunk sai mà không trao toàn bộ nội dung.
- Cần proof membership cho dữ liệu được lưu phân tán.

### 13.3. Root hash phải được bảo vệ

Merkle proof chỉ có giá trị nếu root hash được tin cậy. Nếu attacker thay được cả cây và root mà không có chữ ký hoặc kênh tin cậy, proof không xác thực nguồn gốc.

## 14. Content-addressed storage

Content-addressed storage dùng digest của nội dung làm định danh hoặc một phần định danh artifact.

Ví dụ:

~~~text
objects/
    sha256/
        8b/8b...e4
~~~

Khi nội dung thay đổi, digest thay đổi và tạo một object khác. Điều này hỗ trợ:

- Phát hiện nội dung trùng lặp.
- Cache artifact theo nội dung.
- Tái sử dụng object bất biến.
- Xác minh object khi đọc.
- Liên kết package với chính xác phiên bản nội dung.

### 14.1. Immutability

Object được định danh bằng digest nên nên được xem là bất biến. Nếu nội dung thay đổi, tạo object mới thay vì ghi đè cùng địa chỉ. Điều này làm cache và provenance dễ quản lý hơn.

### 14.2. Digest không thay thế authorization

Biết digest không có nghĩa người dùng được phép đọc object. Storage vẫn cần kiểm soát quyền truy cập, namespace và chính sách chia sẻ.

### 14.3. Collision handling

Hệ thống không nên giả định collision là bất khả thi tuyệt đối. Với hash mật mã hiện đại, xác suất collision tự nhiên rất thấp, nhưng storage có thể xác minh byte khi cùng digest đã tồn tại hoặc có quy trình xử lý collision theo threat model.

### 14.4. Deduplication

Hai package có thể tham chiếu cùng một object nếu byte giống nhau. Điều này tiết kiệm dung lượng nhưng cần tránh làm lộ sự tồn tại của nội dung qua các API không được bảo vệ, vì hành vi deduplication có thể trở thành kênh suy đoán thông tin.

## 15. Atomic write và durability

Kiểm tra hash sau khi ghi giúp phát hiện sai lệch, nhưng cách ghi cũng cần tránh để consumer nhìn thấy tệp dở dang.

### 15.1. Ghi vào tệp tạm

Một quy trình an toàn thường:

1. Ghi toàn bộ nội dung vào tệp tạm trong cùng filesystem.
2. Flush dữ liệu theo yêu cầu durability.
3. Tính và kiểm tra digest của tệp tạm.
4. Đổi tên tệp tạm thành tên chính thức bằng thao tác atomic nếu filesystem hỗ trợ.
5. Ghi metadata hoàn tất.

Nhờ vậy, consumer không đọc một tệp đích mới chỉ được ghi một phần.

### 15.2. Atomicity và durability khác nhau

- Atomicity bảo đảm thay đổi xuất hiện như một bước nguyên tử đối với quan sát viên theo hợp đồng filesystem.
- Durability nói về khả năng dữ liệu vẫn tồn tại sau khi thao tác đã được xác nhận, kể cả sau sự cố nguồn hoặc hệ thống.

Atomic rename không tự bảo đảm nội dung đã được flush bền vững xuống thiết bị. Yêu cầu durability có thể cần flush file và directory metadata theo nền tảng.

### 15.3. Publish marker

Với package gồm nhiều tệp, có thể ghi toàn bộ vào thư mục staging, kiểm tra xong rồi tạo marker hoặc đổi tên thư mục để đánh dấu release đã hoàn tất. Consumer chỉ nhận package có marker hợp lệ.

### 15.4. Không ghi đè artifact đang được sử dụng

Artifact đang chạy hoặc được nhiều consumer đọc nên được version hóa hoặc publish bất biến. Ghi đè nội dung tại cùng đường dẫn có thể khiến consumer khác nhau nhìn thấy các phiên bản khác nhau.

## 16. Kiểm tra schema và tính hợp lệ sau khi xác minh byte

Digest khớp chỉ xác nhận byte khớp với giá trị tham chiếu. Nó không chứng minh artifact có cấu trúc hoặc ngữ nghĩa đúng.

Một pipeline validation có thể gồm:

1. Xác minh chữ ký hoặc HMAC nếu có.
2. Kiểm tra kích thước và digest.
3. Kiểm tra encoding và định dạng container.
4. Parse nội dung.
5. Validate schema version.
6. Resolve dependency và reference.
7. Kiểm tra semantic constraints.
8. Kiểm tra compatibility với runtime và backend.
9. Chỉ sau đó mới cho phép nạp hoặc thực thi.

Ví dụ một file JSON có thể có SHA-256 hợp lệ nhưng thiếu trường bắt buộc image. Đây là lỗi schema, không phải lỗi integrity.

### 16.1. Format version

Artifact nên mang format version để reader biết cách diễn giải. Version không nên chỉ dựa vào tên file hoặc cấu trúc đoán được.

### 16.2. Schema fingerprint

Có thể tính fingerprint cho schema đã canonicalize và ghi fingerprint đó trong artifact metadata. Consumer so sánh fingerprint để biết artifact được tạo theo schema nào.

Fingerprint giúp phát hiện mismatch, nhưng schema fingerprint cũng cần được xác thực nếu attacker có thể thay cả schema và metadata.

### 16.3. Dependency integrity

Một artifact DSL có thể tham chiếu module, plugin hoặc schema bên ngoài. Manifest nên ghi version hoặc content digest của dependency để build và deployment có thể tái lập.

## 17. Kiểm tra toàn vẹn của cache và replica

Cache và replica giúp tăng tốc và khả năng sẵn sàng, nhưng có thể chứa dữ liệu cũ hoặc sai lệch.

### 17.1. Cache validation

Cache key nên bao gồm các yếu tố ảnh hưởng nội dung:

- Source content hash.
- Compiler version.
- DSL version.
- Schema fingerprint.
- Backend và target.
- Compiler flags.
- Dependency digest.

Nếu cache key bỏ sót một yếu tố, cache có thể trả artifact hợp lệ về byte nhưng không phù hợp với đầu vào hoặc môi trường hiện tại.

### 17.2. Replica comparison

Có thể so sánh digest giữa các replica để phát hiện bản sao khác nhau. Nếu khác, hệ thống cần biết replica nào có nguồn gốc đáng tin cậy và phiên bản nào là chuẩn.

### 17.3. Read repair

Một hệ thống lưu trữ phân tán có thể phát hiện replica sai và phục hồi từ replica hoặc nguồn chuẩn khác. Read repair cần dựa trên version hoặc consensus metadata; không nên chỉ chọn digest xuất hiện nhiều nhất nếu có thể tồn tại lỗi tương quan.

### 17.4. Version và stale data

Digest chỉ xác nhận nội dung cụ thể, không cho biết nội dung đó có phải phiên bản mới nhất hay không. Cần version, sequence number, signed release metadata hoặc chính sách freshness riêng để chống replay artifact cũ.

## 18. Replay và rollback artifact

Một artifact cũ có thể có chữ ký hợp lệ và digest đúng nhưng không còn được phép sử dụng. Đây là vấn đề freshness hoặc anti-rollback, khác với integrity thuần túy.

Ví dụ, package v1 đã được ký hợp lệ nhưng v2 chứa bản vá bảo mật. Attacker có thể đưa v1 trở lại nếu runtime chỉ kiểm tra chữ ký.

Các biện pháp:

- Ghi release sequence hoặc version đơn điệu.
- Duy trì minimum accepted version.
- Ký metadata phát hành có version và thời điểm.
- Có chính sách thu hồi artifact hoặc key.
- Kiểm tra trạng thái release với nguồn tin cậy.

Không nên dựa vào timestamp cục bộ do artifact tự khai báo để quyết định mới/cũ. Cần một nguồn trạng thái có độ tin cậy phù hợp.

## 19. Triển khai SHA-256 trong Java

Java cung cấp MessageDigest để tính hash mật mã.

### 19.1. Hash byte array

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class Digests {
    private Digests() {
    }

    public static String sha256(byte[] content)
            throws NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] result = digest.digest(content);
        return HexFormat.of().formatHex(result);
    }
}
~~~

HexFormat có từ Java 17. Với phiên bản Java cũ hơn, có thể dùng Base64 hoặc một formatter hex phù hợp.

### 19.2. Hash tệp theo luồng

Với tệp lớn, không cần nạp toàn bộ nội dung vào bộ nhớ:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class FileIntegrity {
    private FileIntegrity() {
    }

    public static String sha256(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];

        try (InputStream input = Files.newInputStream(path)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Buffer có kích thước cố định nên bộ nhớ sử dụng không tăng theo kích thước tệp. Nếu tệp có thể bị thay đổi trong lúc đọc, cần bảo đảm snapshot hoặc khóa phù hợp để digest phản ánh đúng một phiên bản nhất quán.

### 19.3. So sánh digest

~~~java
import java.security.MessageDigest;
import java.util.HexFormat;

public static boolean matchesSha256(
        byte[] content,
        String expectedHex
) {
    byte[] expected = HexFormat.of().parseHex(expectedHex);
    byte[] actual;

    try {
        actual = MessageDigest.getInstance("SHA-256").digest(content);
    } catch (java.security.NoSuchAlgorithmException e) {
        throw new IllegalStateException(e);
    }

    return MessageDigest.isEqual(expected, actual);
}
~~~

Trong một ứng dụng thực tế, cần kiểm tra định dạng digest và thuật toán được phép trước khi xác minh. Không nên cho phép metadata không tin cậy tùy ý chọn thuật toán yếu.

## 20. Triển khai CRC32C trong Java

CRC32C có thể dùng để phát hiện lỗi ngẫu nhiên trong dữ liệu hoặc frame truyền. Nó không xác thực nguồn và không chống giả mạo có chủ ý.

~~~java
import java.util.zip.CRC32C;

public static long crc32c(byte[] content) {
    CRC32C crc = new CRC32C();
    crc.update(content, 0, content.length);
    return crc.getValue();
}
~~~

CRC32C có sẵn từ Java 9. Khi dùng với giao thức hoặc định dạng đã quy định CRC, phải tuân theo chính xác quy tắc về polynomial, initial value, reflection, final XOR và thứ tự byte. Hai bên chỉ có thể so sánh nếu dùng cùng biến thể.

## 21. Triển khai HMAC trong Java

HMAC có thể xác thực nội dung giữa các thành phần chia sẻ một khóa bí mật.

~~~java
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import java.security.GeneralSecurityException;

public static byte[] hmacSha256(
        SecretKey key,
        byte[] message
) throws GeneralSecurityException {
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(key);
    return mac.doFinal(message);
}
~~~

Khóa cần được sinh, lưu và phân phối bằng cơ chế quản lý secret phù hợp. Không hard-code khóa trong source code hoặc commit vào repository.

Khi xác minh, tính lại tag trên đúng byte sequence và dùng phép so sánh constant-time của thư viện. HMAC không cung cấp confidentiality; nếu nội dung cần được giữ bí mật, phải dùng encryption riêng.

## 22. Chữ ký số trong Java

Java hỗ trợ API Signature để ký và xác minh bằng cặp khóa bất đối xứng. Ví dụ dưới đây minh họa Ed25519:

~~~java
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public static byte[] sign(
        PrivateKey privateKey,
        byte[] payload
) throws Exception {
    Signature signature = Signature.getInstance("Ed25519");
    signature.initSign(privateKey);
    signature.update(payload);
    return signature.sign();
}

public static boolean verify(
        PublicKey publicKey,
        byte[] payload,
        byte[] signedValue
) throws Exception {
    Signature signature = Signature.getInstance("Ed25519");
    signature.initVerify(publicKey);
    signature.update(payload);
    return signature.verify(signedValue);
}
~~~

Ví dụ chỉ tập trung vào thao tác ký và xác minh. Ứng dụng phải lấy public key từ trust store, xác định key ID, kiểm tra chính sách thuật toán và xác minh đúng payload đã canonicalize. Không nhận public key do cùng nguồn không tin cậy cung cấp mà không xác thực nó.

## 23. Kiểm tra toàn vẹn và quản lý khóa

HMAC và chữ ký số phụ thuộc vào khóa. Quản lý khóa là một phần của thiết kế integrity.

### 23.1. Key generation

Khóa cần được tạo bằng nguồn ngẫu nhiên mật mã phù hợp hoặc quy trình quản lý khóa được phê duyệt. Không tự tạo khóa từ password ngắn hoặc chuỗi dễ đoán.

### 23.2. Key storage

Private key và HMAC secret cần được lưu trong secret manager, HSM hoặc kho bảo vệ tương ứng với threat model. Hạn chế quyền đọc và quyền sử dụng khóa.

### 23.3. Key rotation

Khi xoay vòng khóa:

- Phát hành key ID mới.
- Cập nhật trust store của consumer.
- Xác định thời gian chấp nhận đồng thời khóa cũ và mới.
- Ký artifact mới bằng khóa mới.
- Thu hồi khóa cũ khi không còn cần.
- Lưu metadata đủ để xác minh artifact lịch sử theo chính sách.

### 23.4. Revocation

Nếu private key bị lộ, cần có cách thu hồi hoặc đánh dấu không còn tin cậy. Runtime phải biết trạng thái thu hồi từ nguồn đáng tin cậy và xác định chính sách cho artifact đã ký trước thời điểm lộ khóa.

### 23.5. Phân quyền ký và xác minh

Không phải mọi dịch vụ cần quyền ký. Có thể tách:

- Build service tạo artifact.
- Release service kiểm tra và ký.
- Repository lưu artifact bất biến.
- Runtime chỉ có quyền xác minh.

Phân tách trách nhiệm giúp giảm số thành phần có thể tạo artifact được tin cậy.

## 24. Integrity cho artifact có nhiều dependency

Một DSL module có thể phụ thuộc module khác, plugin, schema hoặc runtime library. Chỉ hash tệp gốc không đủ để xác định toàn bộ môi trường thực thi.

### 24.1. Dependency lock

Một lock manifest có thể ghi:

~~~text
module billing@2.4.1
    digest: sha256:...

module tax@1.8.0
    digest: sha256:...

schema orders@5
    digest: sha256:...
~~~

Compiler hoặc runtime tải đúng nội dung có digest tương ứng. Nếu repository trả nội dung khác, kiểm tra thất bại.

### 24.2. Transitive dependencies

Dependency có thể phụ thuộc module khác. Manifest cần bao phủ toàn bộ đồ thị dependency hoặc tham chiếu đến manifest con đã được xác thực. Nếu chỉ ghi dependency trực tiếp mà không khóa các dependency bắc cầu, kết quả build có thể thay đổi.

### 24.3. Build provenance

Có thể lưu:

- Source revision.
- Compiler version.
- Schema fingerprint.
- Dependency digests.
- Build configuration.
- Target platform.
- Artifact digest.

Thông tin này hỗ trợ tái lập build và điều tra nguồn gốc artifact. Provenance cần được ký hoặc bảo vệ nếu dùng làm căn cứ tin cậy.

### 24.4. Reproducible build

Reproducible build hướng đến việc cùng source, toolchain và cấu hình tạo ra byte output giống nhau. Điều này giúp so sánh digest giữa các build độc lập.

Muốn đạt reproducibility, cần kiểm soát timestamp, thứ tự file, metadata, compiler version, dependency và các nguồn nondeterministic. Hash chỉ đo kết quả; nó không tự làm build trở nên tái lập.

## 25. Phát hiện rollback và replay

Một artifact cũ có thể vẫn có hash và chữ ký hợp lệ. Nếu hệ thống cần chỉ chấp nhận phiên bản mới nhất hoặc không thấp hơn một mức bảo mật, phải kiểm tra freshness.

Các cơ chế:

- Monotonic release counter.
- Minimum version policy.
- Signed release index.
- Revocation list.
- Trusted timestamp.
- Deployment state lưu phiên bản đã chấp nhận.

Ví dụ, runtime có thể từ chối plan có release sequence nhỏ hơn phiên bản đã triển khai. Cần có quy trình ngoại lệ rõ cho rollback có chủ đích do quản trị viên phê duyệt.

## 26. Chẩn đoán lỗi integrity

Khi kiểm tra thất bại, thông báo nên đủ để xác định artifact và bước lỗi mà không làm lộ dữ liệu nhạy cảm.

Một diagnostic có thể chứa:

- Artifact ID hoặc tên logic.
- Expected digest và actual digest, nếu được phép hiển thị.
- Thuật toán hash.
- Kích thước dự kiến và thực tế.
- Vị trí lưu hoặc nguồn tải.
- Chunk index nếu lỗi theo chunk.
- Manifest version.
- Release ID.
- Thời điểm kiểm tra.
- Correlation ID để tìm log liên quan.

Ví dụ:

~~~text
artifact: billing.plan
error: INTEGRITY_DIGEST_MISMATCH
algorithm: SHA-256
expected_size: 18432
actual_size: 18432
expected_digest: 8b...e4
actual_digest: 4a...91
action: artifact rejected
~~~

Nếu kích thước bằng nhau nhưng digest khác, dữ liệu vẫn có thể đã bị sửa. Không nên kết luận rằng tệp hợp lệ chỉ vì size khớp.

### 26.1. Không tự động tin bản sao khác

Khi một replica sai digest, hệ thống có thể tải lại từ nguồn khác. Nhưng cần xác minh nguồn thay thế theo trust policy; không nên chấp nhận bản sao chỉ vì nó có cùng version label.

### 26.2. Quarantine

Artifact không hợp lệ có thể được đưa vào vùng quarantine để điều tra, thay vì được runtime nạp hoặc ghi đè ngay. Quarantine cần quyền truy cập hạn chế và retention phù hợp.

### 26.3. Phân biệt lỗi integrity và lỗi validation

- Digest mismatch: byte không khớp giá trị tham chiếu.
- Signature invalid: chữ ký không xác minh được.
- Unsupported format: reader không hỗ trợ format version.
- Schema invalid: cấu trúc không đáp ứng schema.
- Semantic invalid: nội dung không đáp ứng quy tắc DSL.
- Stale artifact: nội dung hợp lệ nhưng phiên bản không được chấp nhận.

Mỗi loại lỗi cần hành động xử lý khác nhau.

## 27. Kiểm thử cơ chế integrity

Kiểm thử cần bao phủ cả dữ liệu hợp lệ, lỗi ngẫu nhiên và tình huống thay đổi có chủ ý.

### 27.1. Kiểm thử round trip

Serialize một artifact, tính digest, lưu, đọc lại và xác nhận digest giống nhau. Sau đó deserialize và xác nhận cấu trúc phù hợp với dữ liệu gốc.

### 27.2. Kiểm thử bit flip

Thay đổi một hoặc nhiều byte trong artifact rồi xác nhận checksum hoặc digest phát hiện sai lệch.

### 27.3. Kiểm thử truncation

Cắt tệp ngắn hơn kích thước manifest và xác nhận kiểm tra thất bại trước khi runtime sử dụng.

### 27.4. Kiểm thử reorder chunk

Hoán đổi hai chunk có checksum riêng hợp lệ. Kiểm tra toàn tệp hoặc Merkle proof phải phát hiện thứ tự ghép không đúng.

### 27.5. Kiểm thử manifest tampering

Thay artifact và tính lại digest trong manifest. Nếu package yêu cầu xác thực nguồn, chữ ký trên manifest phải thất bại sau khi manifest bị sửa.

### 27.6. Kiểm thử key rotation

Xác minh artifact được ký bởi khóa hiện hành, khóa cũ trong giai đoạn chuyển tiếp và khóa đã thu hồi theo đúng chính sách.

### 27.7. Kiểm thử replay

Đưa một package cũ có chữ ký hợp lệ vào deployment và xác nhận minimum version hoặc release sequence policy xử lý đúng.

### 27.8. Kiểm thử lỗi khi ghi

Mô phỏng tiến trình dừng giữa lúc ghi. Consumer không được nhìn thấy artifact dở dang như một bản publish hoàn chỉnh.

### 27.9. Kiểm thử canonicalization

Serialize các cấu trúc logic tương đương với thứ tự key hoặc whitespace khác nhau. Nếu canonicalization được thiết kế để chuẩn hóa các khác biệt đó, digest canonical phải giống nhau; các khác biệt có ý nghĩa như thứ tự câu lệnh DSL vẫn phải được giữ.

## 28. Quy trình kiểm tra toàn vẹn end-to-end cho DSL

Một quy trình triển khai có thể gồm:

1. **Xác định artifact.** Liệt kê source, schema, module, IR, bytecode và package cần bảo vệ.
2. **Xác định threat model.** Phân biệt lỗi ngẫu nhiên, thay đổi trái phép và replay artifact cũ.
3. **Chọn cơ chế.** CRC/checksum cho lỗi ngẫu nhiên; hash cho fingerprint; HMAC hoặc chữ ký số cho xác thực.
4. **Chuẩn hóa serialization.** Xác định encoding, canonicalization và format version nếu cần.
5. **Tạo manifest.** Ghi path, size, digest, algorithm, version và dependency.
6. **Bảo vệ manifest.** Ký hoặc xác thực manifest nếu cần chống sửa đổi có chủ ý.
7. **Ghi artifact an toàn.** Dùng staging, atomic publish và durability phù hợp.
8. **Xác minh khi nhận.** Kiểm tra signature/MAC, size, digest và chunk.
9. **Xác minh khi đọc hoặc nạp.** Không chỉ dựa vào lần kiểm tra tại thời điểm upload.
10. **Validate cấu trúc và ngữ nghĩa.** Parse, schema-check, resolve dependency và kiểm tra compatibility.
11. **Chống stale và rollback.** Kiểm tra version, release sequence và revocation.
12. **Ghi nhận provenance.** Liên kết artifact với source, compiler, schema và dependency.
13. **Quan sát và chẩn đoán.** Phân loại lỗi, ghi correlation ID và quarantine artifact không hợp lệ.
14. **Kiểm thử phục hồi.** Thử corruption, truncation, tampering, retry, replica lỗi và key rotation.

Không phải mọi DSL đều cần chữ ký số, Merkle tree hoặc content-addressed storage. Hãy chọn cơ chế theo giá trị artifact, quy mô dữ liệu, môi trường phân phối và rủi ro thực tế.

## 29. Những sai lầm thường gặp

### 29.1. Dùng checksum để chống attacker

CRC hoặc checksum đơn giản phát hiện lỗi ngẫu nhiên nhưng attacker có thể tính lại chúng. Dùng HMAC hoặc chữ ký số khi cần xác thực.

### 29.2. Tin digest nằm cạnh dữ liệu không được bảo vệ

Nếu attacker sửa được cả artifact và manifest, digest vẫn có thể khớp. Cần bảo vệ giá trị tham chiếu bằng chữ ký, MAC hoặc một nguồn tin cậy độc lập.

### 29.3. Coi hash là encryption

Hash không che giấu nội dung và không thể giải mã ngược. Dùng encryption nếu cần confidentiality.

### 29.4. Hash văn bản sau khi chuyển encoding ngoài ý muốn

Digest phải được tính trên byte sequence đã thỏa thuận. Nếu hai bên tự động đổi newline hoặc encoding ở giữa, kết quả sẽ khác.

### 29.5. Canonicalize làm mất ngữ nghĩa

Sắp xếp danh sách hoặc chuẩn hóa biểu thức một cách tùy tiện có thể thay đổi thứ tự thực thi. Canonicalization phải tuân theo semantics DSL.

### 29.6. Chỉ kiểm tra khi upload

Artifact có thể bị hỏng sau khi lưu hoặc trong quá trình replica. Cần kiểm tra tại ranh giới đọc và trước khi thực thi theo mức rủi ro.

### 29.7. Kiểm tra từng chunk nhưng không kiểm tra toàn tệp

Chunk riêng lẻ hợp lệ vẫn có thể bị ghép sai thứ tự hoặc thiếu chunk. Xác minh toàn bộ artifact hoặc Merkle root.

### 29.8. Bỏ qua manifest và dependency

Source có thể không đổi nhưng schema hoặc module phụ thuộc đã thay đổi. Cần khóa digest của các thành phần tham gia tạo artifact.

### 29.9. Nhầm integrity với freshness

Artifact cũ có thể vẫn có hash và chữ ký hợp lệ. Dùng version policy hoặc anti-rollback state khi cần từ chối phiên bản cũ.

### 29.10. Dùng thuật toán yếu hoặc metadata thuật toán không được kiểm soát

Không nên cho artifact không tin cậy tùy chọn thuật toán yếu. Đặt allowlist và chính sách nâng cấp thuật toán.

### 29.11. Ghi đè tệp đích trực tiếp

Nếu tiến trình dừng giữa chừng, consumer có thể đọc tệp dở dang. Dùng staging và publish nguyên tử khi filesystem hỗ trợ.

### 29.12. Cho rằng digest hợp lệ nghĩa là nội dung an toàn

Digest không kiểm tra schema, logic nghiệp vụ, quyền hoặc mã độc. Vẫn cần validation và kiểm soát thực thi.

## 30. Câu hỏi tự kiểm tra

1. Kiểm tra toàn vẹn là gì và vì sao quan trọng với artifact DSL?
2. Phân biệt integrity, authenticity, confidentiality, availability và validity.
3. Checksum, CRC và hash mật mã khác nhau như thế nào?
4. Vì sao SHA-256 không tự xác thực nguồn gốc artifact?
5. HMAC cung cấp bảo đảm gì và có giới hạn nào?
6. Chữ ký số xác minh điều gì? Vì sao public key phải đến từ trust store?
7. Vì sao serialization không xác định có thể tạo digest khác nhau cho cùng cấu trúc logic?
8. Canonicalization là gì? Nêu các quy tắc cần xác định khi canonicalize DSL artifact.
9. Manifest nên chứa những thông tin nào và vì sao chính manifest cũng cần được bảo vệ?
10. Vì sao cần kiểm tra toàn vẹn end-to-end thay vì chỉ dựa vào transport checksum?
11. Chunk digest và Merkle tree hỗ trợ truyền và xác minh tệp lớn như thế nào?
12. Content-addressed storage hoạt động ra sao? Digest có thay thế authorization không?
13. Atomic write khác durability như thế nào?
14. Vì sao digest khớp chưa chứng minh artifact hợp lệ về schema và ngữ nghĩa?
15. Cache và replica cần những metadata nào để tránh dùng nhầm artifact?
16. Phân biệt integrity với freshness và anti-rollback.
17. Hãy mô tả quy trình kiểm tra một package DSL gồm source, schema, module và bytecode trước khi runtime nạp.
18. Khi kiểm tra digest thất bại, hệ thống nên chẩn đoán, quarantine và phục hồi như thế nào?
