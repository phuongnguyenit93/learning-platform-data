# Versioning tài liệu theo phiên bản API

## 1. Vì sao tài liệu API cần versioning?

API thay đổi theo thời gian: endpoint mới được thêm, field request/response được mở rộng, quy tắc validation thay đổi hoặc một operation cũ bị ngừng hỗ trợ. Nếu tài liệu chỉ có một địa chỉ `/docs/latest`, người dùng API đang chạy phiên bản cũ có thể đọc nhầm contract mới và tích hợp sai.

Trong **SPRING_REST_DOCS**, các test HTTP bằng MockMvc, WebTestClient hoặc REST Assured sinh snippet kiểm chứng request, response, payload, parameters và headers. Snippet được biên soạn bằng Asciidoctor/Markdown và đưa vào build/CI. Chương **CI và phát hành** hướng dẫn cách quản lý tài liệu như một sản phẩm có vòng đời, gắn tài liệu với phiên bản API mà nó mô tả.

Bài này trình bày cách xác định version tài liệu, giữ các bản phát hành cũ, xuất bản đường dẫn versioned, duy trì alias `latest`, xử lý deprecation và kiểm tra tương thích trong CI.

Sau bài học, bạn có thể:

- Phân biệt API version, docs version và version của artifact build.
- Chọn chiến lược URL/versioning phù hợp với chính sách API.
- Sinh tài liệu từ đúng source/ref của API release.
- Giữ tài liệu cũ bất biến và xuất bản bản mới song song.
- Quản lý deprecation, sunset và migration guide.
- Thiết lập CI để kiểm tra tài liệu theo từng API version.

## 2. Phân biệt các loại version

Không nên dùng một con số version cho mọi mục đích mà không định nghĩa ý nghĩa.

| Loại version | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| API version | Contract mà client gọi | `/api/v1/products` hoặc media type version |
| Documentation version | Bản tài liệu mô tả một contract/release | `/docs/1.4/`, `/docs/2.0/` |
| Application release | Phiên bản ứng dụng được triển khai | `catalog-service 2.7.3` |
| Documentation build | Một lần tạo artifact tài liệu | build number hoặc commit SHA |

API version và application release không nhất thiết giống nhau. Một application release có thể phục vụ nhiều API version; ngược lại, nhiều release patch có thể giữ nguyên một API contract. Documentation version nên gắn với mốc contract hoặc release được công bố, không nhất thiết tăng theo từng lần build CI.

Ví dụ: `catalog-service 2.7.3` vẫn cung cấp API `v1`, còn API `v2` đang chạy song song. Trang `/docs/v1/` và `/docs/v2/` phải mô tả đúng contract riêng. Một lần rebuild tài liệu `v1` từ source cũ không nên âm thầm thay đổi nội dung đã phát hành.

## 3. Chọn chiến lược versioning API

API version có thể được biểu diễn ở nhiều vị trí:

| Chiến lược | Ví dụ | Điểm cần cân nhắc |
| --- | --- | --- |
| URL path | `/api/v1/products` | Dễ nhận biết, route tách biệt rõ |
| Query parameter | `/api/products?version=1` | Dễ bị bỏ quên và khó dùng làm contract chính |
| Header | `X-API-Version: 1` | URL ổn định nhưng client phải gửi header |
| Media type | `Accept: application/vnd.example.v1+json` | Phân biệt representation rõ, phức tạp hơn với client/cache |

Spring REST Docs không bắt buộc một chiến lược versioning. Nó ghi nhận request thực tế trong test. Hãy chọn chiến lược ở cấp API design, sau đó bảo đảm test gửi đúng path/header/media type và snippet phản ánh lựa chọn đó.

Ví dụ với URL versioning:

```java
mockMvc.perform(get("/api/v1/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("v1-products-get",
        pathParameters(
            parameterWithName("id").description("Mã sản phẩm")
        ),
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm"),
            fieldWithPath("name").description("Tên sản phẩm")
        )
    ));
```

Operation ID có thể chứa version (`v1-products-get`) để tránh trùng snippet giữa các API version trong cùng output directory. Nếu mỗi version có output directory riêng, vẫn nên dùng naming convention nhất quán.

## 4. Gắn source tài liệu với đúng API release

Tài liệu versioned phải được tạo từ source code và test tương ứng với release đó. Có thể chọn một trong các mô hình:

- **Release tag:** CI checkout tag `v1.4.0`, chạy documentation tests và build docs cho release.
- **Release branch:** duy trì branch hỗ trợ như `release/1.x`, chỉ nhận sửa lỗi và cập nhật docs tương ứng.
- **Monorepo multi-version:** mỗi API version có source/test hoặc module riêng; CI build từng module.
- **Contract snapshot:** lưu contract/schema đã phát hành, sau đó kiểm tra implementation mới so với snapshot.

Không build trang `/docs/1.4/` từ nhánh `main` đang phát triển API `v2` rồi chỉ đổi tên thư mục output thành `1.4`. Tên đường dẫn không làm nội dung trở thành đúng version.

Metadata release nên ghi tối thiểu:

- API version và release/tag tương ứng.
- Commit SHA dùng để tạo tài liệu.
- Thời điểm build và phiên bản toolchain.
- Trạng thái hỗ trợ: current, supported, deprecated hoặc retired.
- Link migration guide nếu có breaking changes.

Commit SHA và build metadata có thể được đưa vào trang version info hoặc artifact manifest. Tránh chèn build timestamp vào mọi snippet nếu nó làm diff tài liệu thay đổi ở mỗi lần build mà không đem lại giá trị.

## 5. Tổ chức output theo version

Một cấu trúc output có thể như sau:

```text
build/site/
└── docs/
    ├── 1.4/
    │   ├── index.html
    │   ├── products.html
    │   └── migration.html
    ├── 2.0/
    │   ├── index.html
    │   ├── products.html
    │   └── migration.html
    └── latest -> 2.0
```

Đây là cấu trúc logic; cách tạo alias hoặc redirect phụ thuộc hosting. Với static hosting, `latest` có thể là redirect page hoặc bản copy được cập nhật sau khi release mới được phê duyệt. Không ghi đè thư mục version cũ bằng nội dung mới.

Ví dụ Gradle có thể nhận version qua property:

```groovy
def docsVersion = providers.gradleProperty('docsVersion')
    .orElse('local')

tasks.named('asciidoctor') {
    attributes 'api-version': docsVersion.get()
    outputDir = layout.buildDirectory.dir("site/docs/${docsVersion.get()}").get().asFile
}
```

Đây là ví dụ cấu hình; tên task và thuộc tính Asciidoctor cần khớp plugin của dự án. Release pipeline phải truyền `docsVersion` lấy từ tag hoặc metadata đã xác nhận, không dựa vào giá trị mặc định `local`.

## 6. Giữ tài liệu đã phát hành bất biến

Khi tài liệu `1.4` đã được công bố, người dùng có thể đã lưu link hoặc dựa vào nó trong quy trình tích hợp. Vì vậy:

- Không tự động thay nội dung version cũ bằng tài liệu từ branch mới.
- Sửa lỗi tài liệu của version cũ bằng một patch có review, tạo lại đúng từ source release/maintenance branch.
- Giữ lại artifact hoặc source snapshot để có thể tái tạo.
- Ghi rõ ngày cập nhật nếu nội dung version cũ được sửa.
- Giữ changelog để người đọc biết phần nào được hiệu chỉnh.

“Bất biến” không có nghĩa không bao giờ sửa typo hoặc lỗi nghiêm trọng. Nó có nghĩa mọi thay đổi phải có chủ đích, được truy vết và không biến tài liệu của API cũ thành contract của API mới.

## 7. Quản lý breaking và non-breaking changes

SemVer có thể là quy ước hữu ích nếu dự án định nghĩa rõ phạm vi áp dụng cho API. Tuy nhiên, không phải mọi API đều có thể suy ra compatibility chỉ từ application version.

Ví dụ thay đổi thường được xem xét:

| Thay đổi | Rủi ro tương thích |
| --- | --- |
| Thêm response field tùy chọn | Thường ít rủi ro với client bỏ qua field lạ, nhưng vẫn cần kiểm tra serializer/client |
| Thêm request field bắt buộc | Breaking với client cũ |
| Xóa hoặc đổi tên field response | Breaking |
| Đổi kiểu field | Có thể breaking |
| Thay status/error code | Có thể phá logic client |
| Thay validation rule | Có thể làm request trước đây hợp lệ bị từ chối |
| Thêm endpoint mới | Thường non-breaking nếu không xung đột |

Spring REST Docs strict field descriptors giúp phát hiện payload thay đổi chưa được tài liệu hóa, nhưng không tự phân loại SemVer. Review viên cần đánh giá tác động client và cập nhật API version/changelog theo chính sách.

## 8. Deprecation và sunset

Khi một API version hoặc operation sắp ngừng hỗ trợ, tài liệu cần công bố rõ:

- Trạng thái deprecated.
- Phiên bản hoặc ngày bắt đầu deprecation.
- Ngày dự kiến sunset/retirement nếu đã được quyết định.
- API thay thế và migration guide.
- Khác biệt về request, response, authentication hoặc error behavior.
- Kênh hỗ trợ và cách kiểm tra client đã chuyển đổi.

Ví dụ nội dung tài liệu viết tay:

```adoc
== API v1 — Deprecated

API v1 vẫn hoạt động trong giai đoạn chuyển tiếp.
Hãy chuyển sang API v2 theo hướng dẫn migration trước ngày sunset
được công bố trong lịch phát hành của dịch vụ.

Xem link:migration-v1-to-v2.html[Hướng dẫn chuyển đổi v1 sang v2].
```

Không tự đặt ngày sunset trong snippet hoặc tài liệu nếu tổ chức chưa phê duyệt. Nếu server gửi deprecation-related headers, có thể dùng `responseHeaders(...)` để tài liệu hóa các header đó, nhưng prose vẫn cần giải thích ý nghĩa và lịch trình.

## 9. Tạo migration guide từ khác biệt contract

Migration guide nên mô tả thay đổi theo tác động tới client, không chỉ liệt kê commit kỹ thuật.

| Nội dung | Câu hỏi cần trả lời |
| --- | --- |
| Endpoint | URL hoặc version header thay đổi thế nào? |
| Request | Field nào được thêm, bỏ, đổi kiểu hoặc đổi validation? |
| Response | Field/status/error code nào thay đổi? |
| Authentication | Scope, token hoặc header nào cần cập nhật? |
| Pagination/filter | Default, sort order hoặc cursor có đổi không? |
| Retry/idempotency | Client cần thay đổi cách retry không? |
| Rollout | Có thể chạy v1/v2 song song trong bao lâu? |

Ví dụ:

```markdown
## Chuyển từ v1 sang v2

| v1 | v2 | Hành động của client |
| --- | --- | --- |
| `GET /api/v1/products/{id}` | `GET /api/v2/products/{id}` | Đổi base path |
| `price` là số nguyên VND | `price.amount` và `price.currency` | Cập nhật model tiền tệ |
| `status=ACTIVE` | `lifecycle=AVAILABLE` | Cập nhật enum mapping |
```

Bảng phải được đối chiếu với snippets của cả hai version. Không chép lại ví dụ request/response dài nếu có thể include snippet tương ứng từ test.

## 10. Kiểm tra version compatibility trong CI

Một pipeline có thể chạy các nhóm kiểm tra:

1. Documentation tests cho API version đang phát triển.
2. Contract tests cho version đang được hỗ trợ.
3. Compatibility checks giữa contract mới và snapshot đã phát hành.
4. Build tài liệu riêng cho mỗi version cần publish.
5. Kiểm tra include/link và version metadata.
6. Kiểm tra không có output mới ghi đè thư mục version cũ.

Ví dụ ma trận:

| Job | Source | Output |
| --- | --- | --- |
| `docs-v1` | release branch/tag `v1.x` | `site/docs/1.x/` |
| `docs-v2` | branch/tag `v2.x` | `site/docs/2.x/` |
| `docs-current` | main | preview, chưa tự động ghi đè release |
| `docs-compatibility` | contract snapshots | report breaking changes |

Không phải dự án nào cũng cần giữ nhiều branch lâu dài. Nếu source cũ không còn build được, có thể lưu artifact tài liệu đã phát hành và chỉ rebuild khi có maintenance change được kiểm soát.

## 11. Tách snippet generation khỏi publish

Nên chia pipeline thành hai giai đoạn:

**Build/verify:** checkout đúng source, chạy test, sinh snippets, kết xuất tài liệu, kiểm tra link và lưu artifact bất biến.

**Publish:** lấy artifact đã được review/approved, triển khai vào đúng thư mục version và cập nhật alias `latest` nếu release được xác nhận.

Điều này tránh việc mọi commit trên `main` tự động thay tài liệu version đang công bố. Với pull request, publish preview vào URL riêng hoặc lưu artifact để reviewer xem trước.

Ví dụ luồng:

```text
Release tag / approved commit
          |
          v
Documentation tests
          |
          v
Generated snippets + Asciidoctor
          |
          v
Link/version/contract checks
          |
          v
Immutable docs artifact
          |
          v
Approval / release gate
          |
          v
Publish /docs/<version>/
          |
          v
Update /docs/latest/ when appropriate
```

## 12. Version metadata trong trang tài liệu

Người đọc cần nhận biết họ đang xem bản nào. Trang landing có thể hiển thị:

- API version được mô tả.
- Release/tag hoặc commit tương ứng.
- Ngày phát hành/cập nhật.
- Trạng thái hỗ trợ.
- Link tới version trước/sau và migration guide.

Ví dụ AsciiDoc:

```adoc
= Catalog API v2
:api-version: 2.0
:api-release: 2.0.0
:api-status: Current

[NOTE]
Đây là tài liệu cho API version {api-version}, release {api-release}.
Trạng thái hỗ trợ: {api-status}.
```

Các attributes phải được truyền từ release metadata đã xác nhận hoặc được review. Không lấy `api-version` từ một giá trị mặc định rồi publish nhầm.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `/docs/v1/` hiển thị contract v2 | Build từ main rồi chỉ đổi tên output | Build từ tag/branch đúng version |
| Tài liệu cũ tự thay đổi | Publish ghi đè thư mục version | Dùng artifact immutable và maintenance release có review |
| Snippet ID đè lên nhau | Nhiều API version dùng chung output directory và operation ID | Tách output directory hoặc thêm prefix version |
| `latest` trỏ nhầm bản preview | Alias cập nhật ở mọi build | Chỉ cập nhật sau release gate |
| Docs version tăng theo mọi build CI | Nhầm build number với contract version | Tách documentation build metadata khỏi API version |
| Migration guide thiếu field | Chỉ đọc source code, không so sánh snippets/contracts | Diff request/response snippets và contract snapshots |
| Ngày sunset không nhất quán | Hard-code nhiều nơi | Quản lý từ release metadata có owner |
| Version cũ không còn build được | Dependency/source cũ đã mất | Lưu artifact phát hành và maintenance branch khi cần |
| Breaking change không bị phát hiện | Chỉ chạy docs tests, không có compatibility check | So sánh contract mới với snapshot đã phát hành |

## 14. Bài thực hành

Giả sử dịch vụ có API v1 và chuẩn bị phát hành v2:

1. Xác định cách version API đang dùng: URL, header hay media type.
2. Tạo test và operation IDs riêng cho v1/v2.
3. Chạy documentation tests từ source/tag tương ứng cho từng version.
4. Tạo output directory `docs/1.x/` và `docs/2.x/` độc lập.
5. Gắn API version, release tag, commit SHA và trạng thái hỗ trợ vào landing page.
6. So sánh request/response snippets giữa hai version.
7. Viết migration guide chỉ ra endpoint, field, status và validation thay đổi.
8. Thêm CI job build từng version và compatibility report.
9. Lưu artifact versioned; không ghi đè tài liệu release cũ từ main.
10. Chỉ cập nhật alias `latest` sau khi release được phê duyệt.

### Câu hỏi tự đánh giá

- API version khác documentation version và build version như thế nào?
- Vì sao phải build tài liệu từ đúng release tag hoặc branch?
- Khi nào nên tách output directory cho từng API version?
- Vì sao `latest` không nên tự cập nhật từ mọi commit main?
- Spring REST Docs strict descriptors giúp gì khi so sánh contract?
- Tại sao docs tests không tự phân loại breaking change?
- Migration guide nên trình bày những nhóm thay đổi nào?
- Deprecation và sunset cần thông tin gì để client lập kế hoạch?
- Khi nào nên lưu artifact bất biến thay vì rebuild tài liệu version cũ?

**Ghi nhớ:** Tài liệu phải gắn với đúng API contract và release đã được kiểm chứng. Build từng version từ source tương ứng, giữ artifact cũ có thể truy vết, dùng migration guide cho thay đổi và chỉ cập nhật `latest` sau release gate. Spring REST Docs cung cấp bằng chứng request/response; chính sách versioning và compatibility vẫn cần được nhóm API xác định và review.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html): cấu hình test và sinh snippets.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): biên soạn và include snippets.
- [Semantic Versioning 2.0.0](https://semver.org/): quy ước version và compatibility.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html): thông tin sunset cho tài nguyên HTTP.
- [RFC 9745 — The Deprecation HTTP Response Header](https://www.rfc-editor.org/rfc/rfc9745.html): header thông báo deprecation.
