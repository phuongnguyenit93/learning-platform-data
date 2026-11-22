# Phân biệt dữ liệu test giả với dữ liệu thật

## 1. Vì sao phải tách dữ liệu test khỏi dữ liệu thật?

Spring REST Docs ghi lại HTTP request và response từ test để sinh tài liệu API. Vì vậy, dữ liệu trong test có thể xuất hiện trong `http-request.adoc`, `request-body.adoc`, `http-response.adoc`, field snippets, custom snippets và artifact CI. Nếu test dùng bản sao dữ liệu production hoặc credential đang hoạt động, tài liệu có thể vô tình công bố thông tin cá nhân, bí mật kinh doanh hoặc quyền truy cập hệ thống.

Trong **SPRING_REST_DOCS**, các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured tạo bằng chứng cho request, response, payload, parameters và headers. Chương **Bảo mật** hướng dẫn bảo vệ dữ liệu được dùng để kiểm thử và tài liệu hóa. Bài này tập trung phân biệt dữ liệu test giả (synthetic/test data) với dữ liệu thật, cách tạo fixture an toàn, giới hạn của việc ẩn danh và cách duy trì tính đại diện của test.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu tổng hợp, dữ liệu giả lập và dữ liệu production.
- Chọn fixture an toàn cho HTTP documentation tests.
- Tránh dùng token, mật khẩu, PII hoặc file thật trong test.
- Hiểu vì sao xóa tên hoặc thay email chưa chắc đã ẩn danh dữ liệu.
- Tạo dữ liệu deterministic nhưng vẫn đủ đa dạng để kiểm tra contract.
- Kiểm tra generated snippets và CI artifacts trước khi chia sẻ.

## 2. Các loại dữ liệu thường gặp

| Loại dữ liệu | Định nghĩa | Ví dụ | Cách sử dụng |
| --- | --- | --- | --- |
| Synthetic data | Dữ liệu được tạo mới, không sao chép bản ghi của người thật | `user-001`, `user@example.test`, đơn hàng giả | Ưu tiên cho test và tài liệu |
| Mock/stub data | Giá trị do test double trả về để kiểm soát một tương tác | Mock service trả `Product(id=42)` | Test tích hợp ở ranh giới đã mock |
| Anonymized data | Dữ liệu thật đã được biến đổi nhằm loại bỏ khả năng nhận diện | Dataset đã qua quy trình ẩn danh được phê duyệt | Chỉ dùng khi có quy trình và đánh giá rủi ro |
| Pseudonymized data | Định danh trực tiếp được thay bằng mã khác, nhưng vẫn có thể liên kết lại bằng thông tin bổ sung | Customer ID thay bằng mã token hóa | Vẫn phải coi là dữ liệu nhạy cảm |
| Production data | Dữ liệu được thu thập từ người dùng/hệ thống thật | Email, địa chỉ, token đang dùng | Không đưa trực tiếp vào test fixture hoặc docs |

Synthetic data thường là lựa chọn phù hợp nhất cho generated documentation. Nó cho phép chọn giá trị rõ nghĩa, ổn định và không mang thông tin của người dùng thật. Mock data hữu ích khi cần cô lập service, nhưng cần phân biệt test mock với test HTTP tích hợp: mock không chứng minh toàn bộ hệ thống xử lý dữ liệu như production.

Ẩn danh và giả danh không giống nhau. Pseudonymization thay định danh trực tiếp nhưng dữ liệu vẫn có thể liên kết lại. Ngay cả dataset đã loại tên vẫn có thể nhận diện cá nhân qua tổ hợp ngày sinh, địa chỉ, lịch sử giao dịch hoặc thuộc tính hiếm.

## 3. Nguyên tắc tạo synthetic data

Synthetic fixture tốt cần đồng thời an toàn và có ích cho test:

1. **Không bắt nguồn từ bản ghi cá nhân thật.** Tạo dữ liệu từ quy tắc hoặc generator, không copy một customer rồi thay tên.
2. **Dùng miền dành cho kiểm thử.** Ví dụ email `user@example.test`; không gửi email tới địa chỉ người thật.
3. **Dùng credential vô hiệu ngoài môi trường test.** Token, API key và password phải là giá trị giả hoặc chỉ có hiệu lực trong sandbox cô lập.
4. **Ổn định khi cần so sánh.** Fixture deterministic giúp snippet và snapshot không thay đổi ngẫu nhiên ở mỗi lần chạy.
5. **Có độ đa dạng có chủ đích.** Bao gồm boundary values, Unicode, chuỗi dài, null/optional, nested objects và trường hợp lỗi.
6. **Không chứa dữ liệu bí mật trong tên file hoặc metadata.** Filename, URL, comment và log cũng có thể được ghi vào snippet.

Ví dụ fixture JSON:

```json
{
  "customerId": "CUST-TEST-0042",
  "email": "linh.nguyen@example.test",
  "displayName": "Nguyen Linh Test",
  "phone": "+12025550142"
}
```

Các giá trị trên được tạo cho mục đích minh họa; không lấy từ khách hàng thật. Với số điện thoại, dùng dải được dành riêng cho ví dụ/test theo quy định của vùng triển khai, tránh vô tình gọi tới số thuê bao thật.

## 4. Không dùng credential thật trong documentation tests

Test xác thực không cần credential production. Có thể dùng:

- Mock security principal hoặc test authentication support.
- JWT được ký bằng key test riêng, không được tin cậy ở production.
- API key giả chỉ tồn tại trong profile test.
- OAuth sandbox riêng với quyền tối thiểu và dữ liệu tổng hợp.

Ví dụ request có token giả:

```java
String testToken = "test-only-token-123";

mockMvc.perform(get("/api/profile")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + testToken)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("profile-get",
        preprocessRequest(
            modifyHeaders().set(
                HttpHeaders.AUTHORIZATION,
                "Bearer <access-token>"
            )
        )
    ));
```

Test vẫn gửi token giả để đi qua security layer; preprocessor thay giá trị trong bản ghi snippet. Hai biện pháp có mục tiêu khác nhau: dữ liệu giả giảm hậu quả nếu redaction bị quên, còn preprocessing bảo đảm tài liệu thể hiện contract mà không lưu giá trị credential.

Không lấy secret từ biến môi trường production chỉ vì CI có thể truy cập. Nếu integration test cần secret sandbox, cấp riêng theo pipeline, giới hạn quyền, thời hạn và quyền đọc log/artifact; tuyệt đối không đưa giá trị đó vào snippet.

## 5. Dữ liệu cá nhân và dữ liệu có thể tái nhận diện

PII không chỉ là tên và email. Các thuộc tính sau có thể nhận diện trực tiếp hoặc khi kết hợp:

- Số điện thoại, địa chỉ, ngày sinh và mã định danh.
- Tọa độ, lịch sử vị trí hoặc mốc thời gian hiếm.
- Mã khách hàng, số hợp đồng, mã giao dịch.
- Nội dung tự do trong ghi chú, tên file hoặc metadata.
- Tổ hợp thuộc tính như khu vực nhỏ, nghề nghiệp và ngày giao dịch.

Thay `name` bằng `Customer A` không đủ nếu giữ nguyên địa chỉ, số hợp đồng hoặc nội dung ghi chú có thể truy ngược. Không đưa dữ liệu production vào fixture rồi chỉ xóa một vài cột.

Nếu tổ chức cần dùng dữ liệu gần production để kiểm tra tính tương thích, phải có quy trình được phê duyệt: phân loại dữ liệu, đánh giá tái nhận diện, biến đổi hoặc tổng hợp dữ liệu, giới hạn quyền truy cập, thời hạn lưu trữ và kiểm tra lại trước khi publish. Pseudonymized dataset vẫn cần được bảo vệ như dữ liệu có khả năng liên kết lại.

## 6. Tạo fixture ổn định cho Spring REST Docs

Generated snippets thường được review trong Git. Nếu fixture sinh ngẫu nhiên ở mỗi lần chạy, diff tài liệu sẽ nhiễu. Dùng giá trị cố định cho các operation quan trọng:

```java
final class ProductFixtures {

    static CreateProductRequest validRequest() {
        return new CreateProductRequest(
            "Mechanical Keyboard",
            1_290_000,
            "catalog@example.test"
        );
    }

    static ProductResponse response() {
        return new ProductResponse(
            42L,
            "Mechanical Keyboard",
            1_290_000,
            true
        );
    }
}
```

Các factory nên trả dữ liệu giả, dễ đọc và đủ ổn định để tài liệu hóa. Với test cần kiểm tra nhiều trường hợp, tạo fixture riêng cho mỗi case thay vì dùng một object lớn rồi sửa ngẫu nhiên các field.

### 6.1. Kiểm tra boundary values

Một fixture duy nhất không bao phủ hết contract. Tạo các case riêng:

| Trường hợp | Ví dụ | Mục đích |
| --- | --- | --- |
| Giá trị hợp lệ | `name = "Keyboard"` | Ví dụ chính trong tài liệu |
| Chuỗi rỗng | `name = ""` | Kiểm tra `@NotBlank` |
| Chuỗi dài tối đa | 120 ký tự | Kiểm tra giới hạn |
| Unicode | `Bàn phím cơ` | Kiểm tra encoding và hiển thị |
| Giá trị biên | `price = 1` | Kiểm tra lower bound |
| Giá trị không hợp lệ | `price = -1` | Kiểm tra validation error |
| Field optional vắng mặt | Không gửi `description` | Kiểm tra optional semantics |

Không cần đưa mọi fixture vào trang tài liệu chính. Có thể dùng nhiều test để xác minh contract, trong khi chỉ chọn request thành công và một số response lỗi đại diện để sinh snippets.

## 7. File upload và binary fixtures

Với multipart API, không dùng ảnh hồ sơ, scan giấy tờ, hợp đồng hoặc file khách hàng thật làm fixture. Tạo file nhỏ tổng hợp, không chứa metadata cá nhân, hoặc dùng file mẫu công khai có quyền sử dụng phù hợp.

Ví dụ:

```java
MockMultipartFile image = new MockMultipartFile(
    "image",
    "sample-product.png",
    MediaType.IMAGE_PNG_VALUE,
    TestFiles.validPngBytes()
);
```

Kiểm tra cả metadata của file: filename, EXIF, author, comment, embedded thumbnail và document properties có thể chứa thông tin cá nhân. Đổi tên file không xóa metadata nhúng bên trong.

Custom snippet cho upload thường chỉ cần part name, media type và kích thước. Không đưa raw bytes hoặc toàn bộ nội dung file vào bảng. Nếu cần ví dụ file, dùng fixture tổng hợp được lưu trong test resources và review nội dung fixture trước khi commit.

## 8. Dữ liệu giả phải phản ánh đúng contract

An toàn không có nghĩa là tùy tiện. Fixture quá đơn giản có thể che lỗi thực tế:

- Chỉ dùng ASCII có thể bỏ sót lỗi Unicode/UTF-8.
- Chỉ dùng chuỗi ngắn có thể bỏ sót giới hạn độ dài.
- Chỉ dùng ID tăng dần có thể bỏ sót UUID hoặc format ID thực tế.
- Chỉ dùng response thành công có thể bỏ sót error contract.
- Mock service mọi nơi có thể bỏ sót serializer, converter hoặc database constraint.

Thiết kế fixture theo schema và quy tắc thực tế nhưng không sao chép bản ghi thật. Có thể dùng generator tạo phân phối dữ liệu tương tự ở mức thống kê, miễn không tạo ra bản sao hoặc dữ liệu có thể liên kết với cá nhân cụ thể. Đối với tài liệu công khai, chọn giá trị đại diện và dễ hiểu.

## 9. Tách môi trường test và production

Không để cấu hình test vô tình kết nối production:

- Dùng profile riêng, ví dụ `test` hoặc `docs`.
- Dùng database/schema riêng và dữ liệu seed tổng hợp.
- Dùng mock server hoặc sandbox cho dịch vụ bên ngoài.
- Tắt email/SMS thật hoặc trỏ tới sink nội bộ.
- Tách bucket/object storage test khỏi production.
- Dùng key ký JWT riêng; production không tin cậy key test.
- Giới hạn network egress của job documentation tests nếu có thể.

Ví dụ property trong test profile:

```yaml
app:
  storage:
    bucket: spring-rest-docs-test
  notifications:
    delivery-mode: disabled
```

Tên property chỉ là ví dụ; ứng dụng cần triển khai cấu hình tương ứng. Không dựa vào tên profile để khẳng định an toàn nếu bean hoặc client vẫn trỏ tới endpoint production.

## 10. Kiểm tra generated snippets không chứa dữ liệu thật

Sau khi test tạo snippet, kiểm tra output directory. Ví dụ:

```java
Path operationDir = snippetsDir.resolve("profile-get");

try (Stream<Path> paths = Files.walk(operationDir)) {
    List<String> files = paths
        .filter(Files::isRegularFile)
        .map(path -> {
            try {
                return Files.readString(path);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })
        .toList();

    assertThat(files)
        .noneMatch(content -> content.contains("production-access-token"))
        .noneMatch(content -> content.contains("real.customer@example.com"));
}
```

Ví dụ dùng AssertJ; các chuỗi kiểm tra phải là sentinel test-only, không phải secret thật. Với fixture synthetic, có thể assert giá trị giả mong đợi xuất hiện và sentinel bị cấm không xuất hiện. Không ghi lại giá trị nhạy cảm vào assertion message.

Quét cả custom snippets, `http-request`, headers, body và output cuối cùng. Nếu Asciidoctor tạo tài liệu hoàn chỉnh, kiểm tra cả thư mục publish vì nội dung có thể được copy hoặc biến đổi ở bước kết xuất.

## 11. Khi nào dữ liệu ẩn danh vẫn không phù hợp?

Không nên mặc định dữ liệu đã mask là an toàn để đưa vào tài liệu. Cần xem xét:

1. Có bảng ánh xạ hoặc khóa phụ cho phép khôi phục danh tính không?
2. Có tổ hợp thuộc tính hiếm khiến một người có thể được nhận diện không?
3. Nội dung tự do có tên, email, số tài khoản hoặc thông tin bí mật không?
4. File có metadata hoặc dữ liệu nhúng không?
5. Dữ liệu có bị ràng buộc bởi hợp đồng, quy định hoặc chính sách nội bộ không?
6. Người đọc tài liệu hoặc artifact có phạm vi truy cập rộng hơn hệ thống nguồn không?

Nếu chưa thể đánh giá rủi ro, không đưa dataset đó vào generated documentation. Tạo fixture tổng hợp thay thế thường đơn giản và an toàn hơn.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Email thật xuất hiện trong snippet | Fixture copy từ production | Thay bằng synthetic address và rà soát lịch sử |
| Token test có quyền production | Tái sử dụng secret môi trường | Tạo credential riêng cho test/sandbox |
| Đã xóa tên nhưng vẫn nhận diện được người | Còn địa chỉ, mốc thời gian hoặc thuộc tính hiếm | Đánh giá tái nhận diện; ưu tiên dữ liệu tổng hợp |
| Snippet thay đổi ở mỗi lần build | Fixture sinh ngẫu nhiên không seed | Dùng fixture deterministic cho docs |
| Test không bắt lỗi Unicode | Chỉ dùng dữ liệu ASCII | Thêm fixture Unicode và encoding cases |
| File fixture lộ metadata | Chỉ đổi filename | Kiểm tra EXIF/document properties và tạo file mới |
| Profile test gọi dịch vụ production | Chỉ đổi profile name nhưng endpoint vẫn trỏ production | Kiểm tra wiring, network và credentials |
| Custom snippet dump toàn bộ object | Không giới hạn field được render | Dùng allowlist model |
| Scanner không phát hiện dữ liệu cá nhân | Pattern scanner không hiểu mọi PII | Kết hợp synthetic fixtures, review và kiểm tra chuyên biệt |

## 13. Asciidoctor và build/CI

Tài liệu include snippets như bình thường:

```adoc
= Product API
:toc: left

== Tạo sản phẩm

=== Request
include::{snippets}/products-create/http-request.adoc[]

=== Request fields
include::{snippets}/products-create/request-fields.adoc[]

=== Response
include::{snippets}/products-create/http-response.adoc[]
```

Với Gradle và plugin Asciidoctor đã cấu hình:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

Pipeline đề xuất:

```text
Documentation tests
        |
        v
Synthetic fixtures + test credentials
        |
        v
HTTP assertions + Spring REST Docs snippets
        |
        v
Secret/PII checks on generated files
        |
        v
Asciidoctor / Markdown build
        |
        v
Artifact review and publish
```

CI cần xác minh job dùng profile và endpoint test, không có kết nối ngoài ý muốn tới production, fixture không chứa dữ liệu thật và generated artifacts đã qua kiểm tra. Secret scanner không thay thế việc phân loại dữ liệu hoặc review fixture.

## 14. Bài thực hành

Với endpoint `POST /api/products`:

1. Tạo DTO fixture bằng factory synthetic, không đọc dữ liệu production.
2. Dùng email thuộc miền `.test`, ID giả và dữ liệu Unicode.
3. Tạo credential chỉ có hiệu lực trong test để kiểm tra authentication.
4. Tạo fixture JSON hợp lệ và các case boundary/invalid riêng.
5. Tạo ảnh PNG tổng hợp; kiểm tra filename và metadata nhúng.
6. Chạy MockMvc test và sinh request/response snippets.
7. Quét toàn bộ operation directory để tìm sentinel bị cấm.
8. Kiểm tra custom snippet chỉ render allowlist fields.
9. Xác nhận profile docs không kết nối database, email, storage hoặc API production.
10. Chạy Asciidoctor trong CI và kiểm tra artifact trước publish.

### Câu hỏi tự đánh giá

- Synthetic data khác pseudonymized data như thế nào?
- Vì sao xóa tên và email chưa chắc đã ẩn danh dữ liệu?
- Tại sao documentation tests nên dùng credential test riêng?
- Làm thế nào tạo fixture deterministic nhưng vẫn kiểm tra boundary values?
- File upload có thể chứa thông tin nhạy cảm ở đâu ngoài bytes chính?
- Vì sao mock data không chứng minh toàn bộ tích hợp production?
- CI cần kiểm tra gì ngoài việc Asciidoctor build thành công?
- Khi nào cần quy trình phê duyệt riêng cho dataset đã ẩn danh?

**Ghi nhớ:** Ưu tiên dữ liệu tổng hợp được tạo mới cho test và tài liệu. Dữ liệu giả danh vẫn có thể liên kết lại; dữ liệu production đã xóa một vài trường vẫn có thể nhận diện. Dùng fixture deterministic, credential test riêng, môi trường tách biệt và kiểm tra generated artifacts trước khi chia sẻ.

## Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): quy trình sinh snippets từ test HTTP.
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): preprocess request/response trước khi ghi snippet.
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework): quản lý rủi ro quyền riêng tư và dữ liệu nhận diện.
- [NIST SP 800-188 — De-Identifying Government Datasets](https://csrc.nist.gov/pubs/sp/800/188/final): cân nhắc kỹ thuật và rủi ro khi de-identification.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý credential và secret.
