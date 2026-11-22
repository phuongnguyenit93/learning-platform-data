# Đồng bộ commit mã và tài liệu được tạo

Tài liệu REST API được sinh bằng Spring REST Docs chỉ đáng tin cậy khi có thể truy ngược về đúng phiên bản mã nguồn đã tạo ra nó. Generated snippets, trang Asciidoctor/Markdown, test reports và artifact phát hành phải thuộc cùng một commit hoặc cùng một build revision được xác định rõ. Nếu ghép snippets từ commit này với HTML từ commit khác, hoặc lấy artifact cũ từ cache, tài liệu có thể trông hợp lệ nhưng mô tả sai API.

Đồng bộ commit có nghĩa là pipeline tạo test output và tài liệu từ một source revision xác định, giữ liên kết giữa các artifact, rồi phát hành đúng bộ output đó. Không chạy test ở một revision rồi checkout branch mới để render hoặc publish bằng thư mục snippet còn sót. Bài học trình bày cách quản lý revision identity, artifact provenance, pipeline nhiều job, versioning và rollback.

Bài học thuộc chương **CI và phát hành** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao code, test, snippets và tài liệu phải cùng revision.
2. Gắn commit SHA/build ID vào test reports và tài liệu được render.
3. Truyền generated snippets giữa các CI jobs mà không trộn revision.
4. Thiết kế pipeline test → snippet → render → artifact → publish có provenance rõ.
5. Phân biệt cache dependency với generated artifact.
6. Quản lý version tài liệu theo release của API.
7. Phát hiện artifact lệch commit, build không tái lập và xử lý rollback.

## 2. Vì sao phải đồng bộ commit?

Một lần thay đổi API có thể làm đổi đồng thời code, test và tài liệu: controller thay path/method; response đổi status/header/JSON; descriptor đổi mô tả field/parameter; preprocessor đổi cách mask token/host; AsciiDoc đổi include hoặc diễn giải.

Spring REST Docs sinh snippets trong lúc test chạy. Vì vậy, snippets phản ánh code và test tại revision đó. Nếu render hoặc publish dùng snippets từ revision khác, liên kết kiểm chứng bị phá vỡ.

### 2.1. Ví dụ artifact bị trộn revision

| Thành phần | Revision |
| --- | --- |
| Application code | Commit A |
| Documentation tests | Commit A |
| Generated snippets | Commit A |
| AsciiDoc source | Commit B |
| Rendered HTML | Commit B |
| Publish artifact | Không rõ nguồn |

HTML có thể include snippet từ A nhưng nội dung AsciiDoc từ B. Reviewer không thể biết tài liệu thể hiện đúng API nào. Một trường hợp khác là HTML render từ B nhưng snippets directory còn file cũ của A do workspace không clean.

Nguyên tắc: mọi đầu vào tạo nên một bộ tài liệu phải có provenance xác định và tương thích revision.

## 3. Xác định revision identity

CI provider thường cung cấp commit SHA của revision đang build. Pipeline nên ghi nhận:

- Full commit SHA hoặc immutable revision ID.
- Branch hoặc pull request number nếu có.
- Build/run ID.
- Version ứng dụng hoặc API release.
- Thời điểm build làm metadata, không thay commit identity.

Không dùng branch name làm định danh duy nhất vì branch có thể di chuyển theo commit mới. Short SHA tiện đọc nhưng nên giữ full SHA trong metadata để tránh va chạm.

### 3.1. Lưu metadata cùng tài liệu

Có thể đưa revision identity vào thuộc tính tài liệu:

```asciidoc
:revnumber: 4.2.0
:commit-sha: abcdef1234567890abcdef1234567890abcdef12
:build-id: 1842

= Orders API
:toc:
```

Giá trị chỉ là ví dụ. CI cần truyền metadata từ revision đang build, không hard-code SHA trong source. Có thể hiển thị commit ngắn trong footer; artifact metadata vẫn giữ full SHA.

### 3.2. Gắn metadata cho artifact

```text
rest-docs-4.2.0-commit-abcdef123456-build-1842/
├── generated-snippets/
├── html/
├── test-reports/
└── build-info.txt
```

Build info có thể chứa commit SHA, build ID, API version, toolchain version và thời điểm build. Không đưa secret hoặc credential môi trường vào metadata.

## 4. Một pipeline, một revision

Pipeline tiêu chuẩn checkout một revision cố định và giữ revision đó xuyên suốt các bước:

```text
Checkout immutable commit SHA
             │
             ▼
Clean workspace/build outputs
             │
             ▼
Compile and run documentation tests
             │
             ▼
Generate snippets
             │
             ▼
Render Asciidoctor / Markdown
             │
             ▼
Validate output and provenance
             │
             ▼
Package one documentation artifact
             │
             ▼
Publish that exact artifact
```

Các bước có thể chạy trong một job hoặc nhiều job. Không checkout một branch đang di chuyển giữa các bước và không dùng snippets từ build khác.

### 4.1. Không checkout lại branch mới giữa pipeline

Ví dụ sai: test job checkout commit A và tạo snippets; render job checkout tên branch main, lúc này đã chuyển sang commit B, rồi include snippets của A. Kết quả là tài liệu có đầu vào từ hai revision.

Cách đúng là render job nhận source artifact hoặc checkout đúng SHA A, rồi nhận snippets artifact cũng được tạo từ SHA A. Nếu pipeline kiểm tra merge result của PR, dùng cùng merge revision cho test và render.

## 5. Đồng bộ snippets và tài liệu giữa nhiều CI jobs

Trong pipeline lớn, có thể tách thành ba job:

1. **Test job:** checkout revision, clean, chạy documentation tests và tạo snippets.
2. **Render job:** lấy source và snippets của cùng revision, chạy Asciidoctor/Markdown.
3. **Publish job:** lấy rendered artifact của cùng build và phát hành.

Mỗi artifact truyền giữa job cần kèm commit SHA/build ID. Render job kiểm tra metadata của snippets trùng với revision source trước khi chạy.

### 5.1. Ví dụ luồng artifact

```text
Test job (commit A)
  ├── generated-snippets/
  ├── test-reports/
  └── provenance: SHA A
          │
          ▼
Render job (source SHA A + snippets SHA A)
  ├── index.html
  ├── assets/
  └── provenance: SHA A
          │
          ▼
Publish job (rendered artifact SHA A)
  └── deployed documentation
```

Nếu metadata không khớp, render/publish phải dừng. Không bỏ qua kiểm tra hoặc đổi tên artifact để che mismatch.

### 5.2. Truyền artifact, không truyền workspace tùy tiện

Workspace giữa các CI jobs thường độc lập. Dùng artifact upload/download của CI provider để truyền snippets và rendered docs. Tránh phụ thuộc vào thư mục runner còn lại hoặc shared directory không có provenance rõ.

## 6. Phân biệt cache và artifact

| Loại | Mục đích | Quy tắc với REST Docs |
| --- | --- | --- |
| Dependency cache | Tăng tốc tải Gradle/Maven dependencies | Có thể chia sẻ theo cache key phù hợp |
| Build cache | Tái sử dụng output task khi input được theo dõi đúng | Chỉ bật khi task khai báo input/output chính xác |
| Generated snippets artifact | Đầu vào để render tài liệu | Gắn với commit/build tạo ra nó |
| Rendered documentation artifact | Đầu ra để review/publish | Phải dùng snippets và source cùng revision |
| Release artifact | Bộ tài liệu chính thức đã phát hành | Immutable hoặc versioned theo release policy |

Không dùng cache như nguồn sự thật cho snippets. Nếu test không chạy nhưng renderer lấy snippet cache cũ, tài liệu có thể không phản ánh thay đổi API.

## 7. Tính tái lập của tài liệu

Một build có thể tái lập khi cùng source revision, dependency/toolchain được khóa và dữ liệu test xác định tạo ra nội dung tương đương. Với Spring REST Docs, cần chú ý:

- Fixture không dùng dữ liệu phụ thuộc thời gian thực nếu không cần.
- ID, timestamp và request ID động được chuẩn hóa khi thích hợp.
- Preprocessors không phụ thuộc hostname hoặc môi trường runner.
- Locale, timezone và encoding được cấu hình ổn định.
- Phiên bản JDK, Gradle/Maven và plugin Asciidoctor được pin.
- Build không lấy snippets hoặc file include từ thư mục cũ.

### 7.1. Không phải mọi byte đều luôn giống nhau

Metadata như thời gian build hoặc file PDF có thể khác giữa các lần chạy. Phân biệt metadata build với nội dung API. Mục tiêu là snippet và contract ổn định; nếu cần byte-for-byte reproducibility, phải chuẩn hóa timestamp và nguồn không xác định khác.

## 8. Version tài liệu theo API release

Tài liệu chính thức thường được version theo release của API hoặc sản phẩm:

```text
docs/
├── 4.1/
│   └── index.html
├── 4.2/
│   └── index.html
└── current/
    └── index.html
```

Alias current có thể trỏ tới release hiện hành, trong khi version cũ vẫn được giữ cho người dùng đang tích hợp. Không dùng commit SHA làm version public duy nhất nếu sản phẩm có version semantics riêng; SHA dùng để truy vết build.

Khi release mới: chọn source revision/tag; chạy documentation tests; render và kiểm tra artifact; gắn API/documentation version; publish đúng đường dẫn version; cập nhật alias current sau khi release hoàn tất.

## 9. Kiểm tra provenance trước publish

Trước khi publish, xác minh:

- Commit SHA trong build metadata khớp revision checkout.
- Test report thuộc cùng commit.
- Snippets artifact được tạo từ cùng commit.
- AsciiDoc/Markdown source dùng để render thuộc cùng revision.
- Rendered HTML/PDF được tạo từ snippets đó.
- API/documentation version khớp release dự kiến.
- Artifact được publish chính là artifact đã được review.

Có thể tạo manifest:

```text
commit=abcdef1234567890abcdef1234567890abcdef12
build=1842
api-version=4.2.0
test-status=passed
snippets-artifact=rest-docs-snippets-1842
rendered-artifact=rest-docs-html-1842
```

Manifest là metadata để đối chiếu, không thay thế chữ ký hoặc artifact attestation nếu tổ chức yêu cầu mức bảo đảm cao hơn.

## 10. Pull request, merge và release

| Giai đoạn | Revision nên dùng | Đầu ra |
| --- | --- | --- |
| PR validation | PR head hoặc merge revision đã xác định | Test report, preview docs |
| Main branch build | Commit đã merge | Artifact docs cho main |
| Release build | Tag/commit release bất biến | Versioned documentation |
| Publish | Artifact của release build đã kiểm tra | Tài liệu chính thức |

Nếu PR được kiểm tra bằng synthetic merge commit, dùng đúng merge commit đó cho test và render. Sau merge, pipeline main branch build lại từ commit đã merge để tạo artifact chính thức.

## 11. Rollback và sửa tài liệu đã phát hành

Khi phát hiện tài liệu release sai:

1. Xác định version, commit và build ID đã publish.
2. Tạm dừng hoặc đánh dấu artifact bị ảnh hưởng nếu cần.
3. Sửa source/test/descriptor trong một commit mới.
4. Chạy lại test, render và validation.
5. Publish bản sửa theo version/revision policy phù hợp.
6. Giữ lịch sử hoặc ghi chú thay đổi để người dùng biết tài liệu đã được sửa.

Không ghi đè artifact cũ mà không lưu provenance. Với tài liệu versioned, có thể phát hành patch documentation release hoặc cập nhật cùng version theo chính sách sản phẩm; cần nêu rõ thay đổi.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| HTML không khớp code | Render và test dùng revision khác nhau | Khóa cùng commit SHA |
| Snippet cũ xuất hiện | Workspace/cache chứa output từ build khác | Clean và tạo artifact mới |
| Render job thiếu snippets | Không truyền artifact từ test job | Upload/download artifact cùng run |
| Artifact có SHA khác nhau | Metadata không được kiểm tra | Thêm provenance validation |
| Branch build thay đổi giữa job | Checkout branch name thay vì SHA | Checkout immutable revision |
| Preview đúng nhưng release sai | Publish lấy artifact của run khác | Publish exact artifact đã review |
| Diff snippet liên tục | Fixture/timezone/ID không ổn định | Chuẩn hóa dữ liệu test |
| Version docs không khớp API | Gắn version thủ công sai | Lấy version từ release metadata |
| Rollback không rõ nguồn | Artifact bị ghi đè, thiếu manifest | Lưu immutable/versioned artifacts |
| Cache làm render pass giả | Snippets cache được dùng dù test không chạy | Không coi cache là nguồn snippet |

## 13. Bài thực hành

Thiết kế pipeline nhiều job cho API orders. Test job tạo snippets cho commit; render job tạo HTML; publish job phát hành version tài liệu tương ứng release.

**Nhiệm vụ:**

1. Checkout immutable commit SHA trong test job.
2. Clean output và chạy documentation tests.
3. Upload snippets cùng manifest có commit SHA/build ID.
4. Render job checkout đúng SHA và tải đúng snippets artifact.
5. Kiểm tra metadata snippets khớp source revision trước render.
6. Tạo HTML/PDF và lưu provenance cùng artifact.
7. Publish job chỉ dùng rendered artifact từ cùng pipeline run đã được kiểm tra.
8. Gắn API/documentation version theo release tag.
9. Thử tình huống artifact SHA không khớp và xác nhận pipeline dừng.
10. Viết quy trình rollback khi phát hiện tài liệu đã phát hành sai.

**Tiêu chí hoàn thành:** source, tests, snippets, rendered docs và published artifact có provenance thống nhất; không trộn revision; version tài liệu rõ; mismatch ngăn publish; có thể truy vết và rollback.

## 14. Ghi nhớ

- Snippet được sinh từ test của một source revision cụ thể; tài liệu render phải dùng đúng source và snippets revision đó.
- Gắn full commit SHA và build ID vào metadata/artifact để truy vết.
- Khi tách CI jobs, truyền snippets bằng artifact có provenance, không dựa vào workspace dùng chung.
- Phân biệt dependency cache với generated snippets và rendered artifacts.
- Dùng immutable revision thay vì branch name có thể di chuyển.
- Version tài liệu theo API release; dùng SHA để truy vết build.
- Kiểm tra provenance trước publish và chỉ publish artifact đã được kiểm tra.
- Lưu lịch sử artifact để điều tra, sửa và rollback tài liệu sai.
