# Kiểm tra tài liệu trong pull request

Tài liệu REST API được tạo từ Spring REST Docs cần thay đổi cùng nhịp với code và hợp đồng API. Pull request (PR) là thời điểm phù hợp để kiểm tra mối liên hệ đó: documentation tests phải chạy, snippet phải được tạo mới, Asciidoctor phải render thành công và reviewer cần xem được thay đổi trước khi merge.

Một PR có thể làm thay đổi endpoint, status, header, payload hoặc semantics của field mà không cập nhật phần diễn giải. Nếu chỉ kiểm tra ứng dụng build thành công, những thay đổi này có thể lọt qua review. Đưa việc tạo và kiểm tra tài liệu vào CI của PR giúp phát hiện snippet thiếu, include lỗi, ví dụ cũ và dữ liệu nhạy cảm trước khi code được hợp nhất.

Bài học thuộc chương **CI và phát hành** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế CI checks chạy khi có pull request.
2. Chạy documentation tests và render tài liệu trong PR pipeline.
3. Phát hiện snippet thiếu, cũ hoặc không còn được include.
4. So sánh tài liệu được render giữa base branch và branch của PR.
5. Đưa HTML/PDF hoặc preview vào PR để reviewer xem xét.
6. Thiết lập failure gates cho test, render và kiểm tra dữ liệu nhạy cảm.
7. Phân biệt kiểm tra tài liệu trong PR với bước publish tài liệu chính thức.

## 2. Vì sao cần kiểm tra tài liệu trong pull request?

Một thay đổi API có thể ảnh hưởng tới status code, response header, field, kiểu dữ liệu, query/path parameter hoặc identifier của snippet. Nếu không tạo lại tài liệu trong PR, reviewer phải suy đoán tác động hoặc chờ đến pipeline phát hành.

PR check cung cấp bằng chứng sớm rằng tests, snippets và trang tài liệu vẫn nhất quán. Nó cũng tạo cơ hội review diff của contract trước khi merge.

## 3. Luồng CI cho pull request

```text
Pull request opened / updated
             │
             ▼
Checkout PR revision
             │
             ▼
Clean generated output
             │
             ▼
Run unit + documentation tests
             │
             ├── Failure ──► Fail required check
             │
             ▼
Generate fresh snippets
             │
             ▼
Validate includes and sensitive data
             │
             ▼
Render Asciidoctor / Markdown
             │
             ▼
Compare rendered docs (optional)
             │
             ▼
Upload preview artifact
             │
             ▼
Reviewer inspects changes
             │
             ▼
Merge when required checks pass
```

PR pipeline thường tạo preview artifact thay vì tự động phát hành lên website production. Publish chính thức nên là bước riêng sau merge hoặc sau release được phê duyệt.

### 3.1. Những gì nên chạy ở mỗi PR?

Tối thiểu gồm documentation tests liên quan, Asciidoctor/Markdown rendering, kiểm tra include bắt buộc, secret scan trên snippet/output và lưu test report cùng preview artifact.

Với repository lớn, có thể chạy toàn bộ docs tests. Chỉ chạy subset theo module/path khi có cơ chế xác định phụ thuộc đáng tin cậy; nếu không, thay đổi dùng chung có thể ảnh hưởng operation khác mà pipeline không kiểm tra.

## 4. Chạy test và render từ revision của PR

PR job phải checkout đúng commit hoặc merge revision được kiểm tra. Không lấy snippet từ branch chính hoặc artifact của lần build trước.

Ví dụ Gradle:

```bash
./gradlew clean test asciidoctor
```

Ví dụ Maven:

```bash
./mvnw clean verify
```

Các lệnh giả định build đã cấu hình task/lifecycle để documentation tests chạy trước Asciidoctor. Nếu dự án tách task docs riêng, hãy gọi đúng task tạo snippet và bảo đảm renderer phụ thuộc vào nó.

### 4.1. Clean output trước khi tạo snippet

Nếu test bị xóa hoặc đổi identifier, snippet cũ có thể còn trong workspace và khiến Asciidoctor render thành công dù operation mới không tạo file. CI nên tạo output từ clean state hoặc xóa generated-snippets directory trước documentation tests. Không phục hồi snippet từ cache không rõ commit.

## 5. Kiểm tra snippet và include

Sau test, PR pipeline nên xác minh các file mà AsciiDoc include thật sự tồn tại. Ví dụ:

```asciidoc
=== Request

include::{snippets}/orders-get/http-request.adoc[]

=== Response

include::{snippets}/orders-get/http-response.adoc[]

=== Response fields

include::{snippets}/orders-get/response-fields.adoc[]
```

Nếu test không sinh response-fields.adoc vì descriptor không được khai báo, include đó sẽ thất bại. Đây là lỗi cần sửa ở test hoặc nội dung tài liệu; không tạo file rỗng để làm CI xanh.

### 5.1. Kiểm tra identifier

Identifier truyền vào document("orders-get", ...) thường tạo thư mục snippet có cùng tên. Khi đổi identifier, phải cập nhật include. Một script/task validation có thể đọc danh sách include và xác minh file tồn tại trước render.

## 6. Review thay đổi tài liệu trong PR

Có hai loại thay đổi cần reviewer xem:

1. **Source documentation:** AsciiDoc/Markdown, descriptor và test được cập nhật.
2. **Rendered documentation:** HTML/PDF được tạo từ source và snippet của PR.

Diff source có thể không cho thấy tác động trực quan của Asciidoctor. Vì vậy, lưu HTML/PDF hoặc tạo preview để reviewer kiểm tra headings, code blocks, tables, links và snippet đã include.

### 6.1. So sánh với base branch

Có thể render tài liệu từ base branch và PR branch rồi so sánh output để nhận diện endpoint mới/bị loại, status/header/field thay đổi, snippet do contract đổi, nội dung mất do include sai và diff nhiễu do timestamp hoặc ID ngẫu nhiên.

Để diff có giá trị, test fixture và preprocessors nên tạo output ổn định. Nếu dữ liệu động không được chuẩn hóa, PR có thể chứa nhiều thay đổi nhiễu khiến reviewer bỏ qua thay đổi thực sự.

### 6.2. Không coi mọi diff là lỗi

API contract thay đổi hợp lệ sẽ làm tài liệu thay đổi. PR check nên cung cấp diff và yêu cầu review, không tự động chặn mọi thay đổi snippet. Failure gate dành cho test fail, render fail, file thiếu hoặc vi phạm policy; tính đúng chủ đích là quyết định review.

## 7. Đưa preview vào pull request

Tùy CI provider, có thể upload HTML/PDF thành artifact, publish preview lên môi trường tạm thời gắn với PR, đính kèm link preview hoặc lưu generated snippets cùng test report để debug.

Nếu dùng preview deployment, mỗi PR nên có URL/identifier riêng, thời hạn dọn dẹp và không ghi đè tài liệu production. Quyền truy cập preview cần phù hợp với độ nhạy cảm của API documentation.

### 7.1. Artifact phải gắn với commit

Preview, snippets và test report phải thuộc cùng revision. Gắn commit SHA/build ID vào metadata hoặc tên artifact để tránh reviewer xem HTML từ commit khác với source đang review.

## 8. Failure gates cho PR checks

Các điều kiện nên làm required check thất bại:

1. Unit/documentation test bắt buộc thất bại.
2. Documentation tests bị skip ngoài dự kiến.
3. Snippet identifier hoặc file include bắt buộc bị thiếu.
4. Asciidoctor/Markdown render thất bại.
5. Secret scan phát hiện token, API key hoặc dữ liệu bị cấm.
6. Preview artifact không được tạo khi pipeline yêu cầu.
7. Test report hoặc artifact không khớp revision đang kiểm tra.

Không dùng continue-on-error cho bước xác minh bắt buộc. Nếu một nhóm test không liên quan được phép skip, hãy tách job rõ ràng để documentation tests vẫn là required check.

### 8.1. Build xanh không thay thế review nội dung

Build xanh chỉ chứng minh các bước tự động đã pass. Nó không chứng minh mô tả endpoint rõ ràng hoặc ví dụ phù hợp với người tích hợp. Reviewer vẫn cần xem nội dung thay đổi, đặc biệt khi status, header, field hoặc semantics API đổi.

## 9. Kiểm tra dữ liệu nhạy cảm trước khi preview

PR artifact có thể được nhiều người truy cập hơn môi trường test. Kiểm tra Authorization, Cookie, Set-Cookie, API key, access/refresh token, authorization code, URL callback chứa token/signature, email, số điện thoại, tenant/user ID thật và hostname/IP nội bộ không nên công bố.

Ưu tiên fixture giả ngay từ đầu. Preprocessors có thể thay/loại giá trị trong snippet nhưng không nên là lớp bảo vệ duy nhất. Secret scan cần chạy trên generated snippets và HTML/PDF đã render, không chỉ trên source code.

Nếu phát hiện secret thật trong artifact PR, dừng pipeline, loại artifact/preview và xử lý credential theo quy trình của tổ chức. Không chỉ sửa file rồi để artifact cũ tiếp tục truy cập được.

## 10. Ví dụ workflow PR tổng quát

Ví dụ dưới đây mô tả các bước logic, không phải cấu hình chạy nguyên trạng cho một CI provider cụ thể:

```yaml
pull_request:
  jobs:
    rest-docs-check:
      steps:
        - checkout pull request revision
        - run: ./gradlew clean test asciidoctor
        - run: ./gradlew verifyDocs
        - run: scan generated snippets and rendered docs
        - upload: build/docs and test reports
```

Tên event, checkout action, upload syntax và task verifyDocs phụ thuộc nền tảng CI/build script. Cần bảo đảm job chạy trên PR revision, test thực sự tạo snippet, renderer chạy sau test và artifact được gắn với commit đó.

### 10.1. Required status check

Đặt job tài liệu thành required status check trong branch protection/ruleset nếu chính sách repository yêu cầu tài liệu luôn được kiểm tra trước merge. Khi đó PR không thể merge nếu documentation tests, render hoặc validation bắt buộc thất bại.

Quyền cấu hình branch protection thường thuộc repository administrator. Bài học mô tả cách tổ chức check; việc bật rule cần thực hiện trong cấu hình repository tương ứng.

## 11. Phân biệt PR validation và publish

| Giai đoạn | Mục tiêu | Đầu ra |
| --- | --- | --- |
| Pull request | Kiểm tra tính đúng và tạo preview để review | Test report, snippets, HTML/PDF preview |
| Sau merge | Xác nhận trạng thái trên nhánh chính | Artifact build từ commit đã merge |
| Release/publish | Phát hành tài liệu chính thức | Website hoặc tài liệu versioned |

PR pipeline không nên tự động thay thế tài liệu production nếu chưa có quy trình publish được phê duyệt. Preview giúp review; publish là hành động riêng có kiểm soát version và quyền truy cập.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| PR xanh nhưng snippet cũ | Không clean output hoặc dùng cache cũ | Tạo snippet từ clean state |
| Asciidoctor báo thiếu include | Test không chạy hoặc identifier lệch | Kiểm tra test report và include path |
| Preview không khớp source PR | Artifact lấy từ commit khác | Gắn commit SHA và truyền artifact cùng run |
| Diff tài liệu quá nhiều | Timestamp/ID ngẫu nhiên | Fixture xác định và preprocessors |
| PR fail vì snippet thay đổi hợp lệ | Coi mọi diff là lỗi | Cho reviewer đánh giá diff contract |
| Secret xuất hiện trong preview | Chỉ scan source hoặc raw request | Scan generated snippets và rendered output |
| Documentation tests không chạy | Filter/profile/skip property | Kiểm tra test count và required job |
| Preview tồn tại sau khi PR đóng | Không có cleanup lifecycle | Thiết lập expiration và cleanup |
| PR merge dù docs job fail | Job không phải required check | Cấu hình branch protection/ruleset |
| Markdown preview thiếu snippet | Dùng cú pháp Asciidoctor như Markdown mặc định | Thêm bước chèn/chuyển đổi riêng |

## 13. Bài thực hành

Thiết lập PR check cho API orders. PR thay đổi response field và thêm một response header. Tài liệu AsciiDoc include request, response, headers và fields.

**Nhiệm vụ:**

1. Tạo job chạy trên pull request revision.
2. Clean generated output trước documentation tests.
3. Chạy test tạo snippet và render Asciidoctor sau test.
4. Kiểm tra mọi include identifier/file tồn tại.
5. Tạo HTML/PDF preview và upload thành artifact của PR.
6. So sánh diff tài liệu với base branch.
7. Xác nhận response field/header mới xuất hiện đúng trong snippet và descriptor.
8. Scan token, cookie và dữ liệu fixture trong snippets lẫn rendered artifact.
9. Thiết lập job thành required check nếu repository policy yêu cầu.
10. Phân biệt preview PR với bước publish tài liệu chính thức sau merge/release.

**Tiêu chí hoàn thành:** PR pipeline chạy đúng revision; test và render thành công; snippet mới được tạo; diff/preview sẵn sàng review; secret scan pass; lỗi bắt buộc ngăn merge; không tự động ghi đè tài liệu production.

## 14. Ghi nhớ

- Pull request là nơi kiểm tra tài liệu cùng thay đổi API trước khi merge.
- Chạy documentation tests từ PR revision, tạo snippet mới rồi render Asciidoctor/Markdown.
- Clean output để tránh snippet cũ làm PR check xanh giả.
- Xác minh include, identifier, test report và artifact provenance.
- Review diff snippet/rendered docs để nhận biết thay đổi contract và lỗi trình bày.
- Scan generated snippets và HTML/PDF để phát hiện secret hoặc dữ liệu riêng tư.
- Dùng preview artifact hoặc preview deployment riêng cho PR.
- PR validation và publish chính thức là hai giai đoạn khác nhau.
