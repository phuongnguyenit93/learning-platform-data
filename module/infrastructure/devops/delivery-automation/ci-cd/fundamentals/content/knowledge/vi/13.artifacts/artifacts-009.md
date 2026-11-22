# Giới thiệu bằng chứng nguồn gốc build và danh mục thành phần phần mềm

Một artifact được build thành công chưa tự trả lời được các câu hỏi quan trọng trước khi phát hành: mã nguồn nào đã tạo ra nó, pipeline và builder nào đã chạy, dependency nào được sử dụng, artifact có bị thay đổi sau build hay không và có thể xác minh những thông tin đó bằng cách nào?

Hai loại dữ liệu giúp trả lời các câu hỏi này là **bằng chứng nguồn gốc build (build provenance)** và **danh mục thành phần phần mềm (Software Bill of Materials - SBOM)**. Provenance mô tả artifact được tạo ra như thế nào và từ những đầu vào nào. SBOM mô tả các thành phần phần mềm có trong artifact. Khi gắn cả hai với digest bất biến của artifact và bảo vệ bằng chữ ký/attestation, nhóm có thể truy vết và kiểm tra chuỗi cung ứng phần mềm trước khi triển khai.

Đây là nội dung thuộc **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng CI/CD từ sự kiện Git và pipeline dưới dạng mã đến build, kiểm thử, quản lý artifact, môi trường, quality gate, bảo vệ bí mật, xác minh sau triển khai và quay lui. Provenance và SBOM bổ sung bằng chứng để quyết định phát hành dựa trên dữ liệu có thể kiểm tra.

## 1. Artifact cần có danh tính ổn định

Artifact là đầu ra được tạo từ quá trình build, chẳng hạn:

- JAR, WAR hoặc package của ứng dụng Java.
- Binary, executable hoặc gói cài đặt.
- Container image.
- Static site hoặc bundle frontend.
- Helm chart, manifest hoặc gói triển khai.
- Báo cáo kiểm thử, SBOM và metadata phục vụ phát hành.

Tên file hoặc tag dễ đọc giúp con người nhận biết phiên bản, nhưng có thể bị ghi đè hoặc trỏ sang nội dung khác. Để nhận diện chính xác nội dung, dùng **digest mật mã** được tính trên artifact, thường là SHA-256.

Ví dụ:

~~~text
Artifact: registry.example.com/orders/api:1.8.0
Digest:   sha256:7b2d...e91a
Commit:   4f9a1c2...
Build:    ci-run-1842
~~~

Tag 1.8.0 là nhãn tham chiếu. Digest xác định nội dung cụ thể. Nếu tag được cập nhật để trỏ sang image khác, digest của image mới sẽ khác. Vì vậy, các bước kiểm thử, xác minh provenance, quét bảo mật và triển khai nên tham chiếu cùng digest.

Với một file JAR, digest có thể được tính bằng:

~~~bash
sha256sum build/libs/orders-api.jar
~~~

Với container image, registry thường cung cấp digest của manifest hoặc image index. Hãy dùng digest mà registry công bố cho đúng nền tảng và manifest được triển khai. Một image đa kiến trúc có thể có image index digest và digest riêng cho từng platform manifest; cần hiểu digest nào đang được kiểm tra và triển khai.

Danh tính ổn định là điểm nối giữa artifact, provenance, SBOM, scan report, chữ ký, release và deployment record. Nếu các tài liệu này chỉ liên kết bằng tên tag có thể thay đổi, chuỗi truy vết sẽ không đáng tin cậy.

## 2. Build provenance là gì?

Build provenance là bản ghi có cấu trúc về quá trình tạo ra artifact. Nó mô tả những thông tin như:

- Artifact nào là đầu ra của lần build.
- Builder hoặc hệ thống CI nào thực hiện build.
- Workflow, job hoặc quy trình build nào đã chạy.
- Mã nguồn và revision nào được sử dụng.
- Dependency hoặc tài liệu đầu vào nào đã được resolve.
- Tham số build và cấu hình có ảnh hưởng đến kết quả.
- Thời điểm bắt đầu, kết thúc và định danh lần chạy.

Một provenance tốt giúp người nhận artifact kiểm tra: artifact này có được tạo từ repository chính thức không? Có đúng commit đã được review không? Builder có nằm trong danh sách tin cậy không? Build có sử dụng dependency hoặc tham số ngoài dự kiến không?

Provenance không phải chỉ là một dòng log “build succeeded”. Log thường được tối ưu cho điều tra và có thể khó chuẩn hóa, tổng hợp hoặc xác minh tự động. Provenance dùng cấu trúc dữ liệu có schema, gắn với subject digest và có thể được ký hoặc phát hành dưới dạng attestation.

### 2.1. Các thành phần chính của provenance

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Subject | Artifact được mô tả, thường kèm digest | Image orders-api với SHA-256 |
| Builder identity | Hệ thống hoặc dịch vụ đã tạo artifact | CI workflow chạy trên builder được tin cậy |
| Build type | Quy trình hoặc loại build được sử dụng | Build container image theo workflow chuẩn |
| Source/materials | Mã nguồn, revision và dependency đầu vào | Repository, commit SHA, base image digest |
| Parameters | Tham số ảnh hưởng đến build | Target, build arguments được phép công khai |
| Invocation | Định danh lần chạy | Pipeline run ID, workflow run ID |
| Timing | Thời điểm build bắt đầu và kết thúc | Timestamp UTC |
| Metadata | Các thông tin bổ sung theo schema | Phiên bản builder, liên kết log hoặc run |

Provenance cần mô tả đầu vào đã resolve thực tế, không chỉ ghi một tham chiếu di động. Ví dụ, ghi base-image:latest không cho biết chính xác image nào đã được sử dụng. Ghi digest của base image giúp xác định nội dung đầu vào.

Không đưa secret vào provenance. Có thể ghi tên tham số hoặc chỉ ra rằng một credential được cấp qua secret manager, nhưng không ghi token, password, private key hay giá trị bí mật vào metadata.

## 3. Attestation và chữ ký số

**Attestation** là một tuyên bố có cấu trúc về một đối tượng, được phát hành bởi một bên xác định. Với build provenance, attestation tuyên bố artifact có digest cụ thể được tạo ra theo một quy trình và từ các đầu vào đã ghi nhận.

Một attestation thường có ba phần cần phân biệt:

1. **Nội dung:** tuyên bố gì về artifact, chẳng hạn build provenance hoặc SBOM.
2. **Người phát hành:** hệ thống hoặc danh tính nào tạo ra tuyên bố.
3. **Tính toàn vẹn và xác thực:** chữ ký hoặc cơ chế bảo vệ nào cho phép phát hiện nội dung bị sửa và xác minh nguồn phát hành.

Chữ ký số không chứng minh mọi tuyên bố đều đúng về mặt học thuật hoặc artifact không có lỗi. Nó chứng minh dữ liệu đã ký không bị thay đổi sau khi ký và được ký bởi danh tính tương ứng với khóa/chứng thư đã xác minh. Người tiêu thụ vẫn phải quyết định danh tính đó có đáng tin, builder có được phép build repository này và quy trình có đáp ứng policy hay không.

### 3.1. Chuỗi xác minh

Một quy trình xác minh điển hình:

1. Tính hoặc lấy digest của artifact đang kiểm tra.
2. Tải attestation liên quan đến đúng digest.
3. Xác minh chữ ký hoặc envelope theo trust root được cấu hình.
4. Kiểm tra danh tính người phát hành, issuer và builder.
5. Kiểm tra repository, source revision, workflow và build type.
6. Kiểm tra materials, tham số và các điều kiện policy.
7. Đối chiếu SBOM và kết quả scan với cùng artifact digest.
8. Chỉ cho phép triển khai nếu tất cả điều kiện bắt buộc đạt.

Không được chỉ kiểm tra “có chữ ký” rồi mặc định tin cậy. Chữ ký hợp lệ từ một workflow không được phép phát hành production vẫn không đáp ứng policy. Cần xác minh cả tính hợp lệ của chữ ký và danh tính/nguồn phát hành được phép.

### 3.2. in-toto và SLSA

**in-toto** cung cấp mô hình mô tả các bước và vật liệu trong chuỗi cung ứng phần mềm, cùng cơ chế attestation để ghi lại tuyên bố về hoạt động đó. Một in-toto Statement liên kết subject với predicate chứa dữ liệu cụ thể, chẳng hạn provenance hoặc SBOM.

**SLSA (Supply-chain Levels for Software Artifacts)** là một khuôn khổ giúp đánh giá và cải thiện mức độ bảo đảm của quy trình build. SLSA provenance mô tả nguồn gốc build theo schema xác định; các yêu cầu về builder, build process và bảo vệ provenance giúp người tiêu thụ đánh giá mức độ tin cậy của artifact.

Các khái niệm này có liên quan nhưng không đồng nghĩa:

- in-toto mô tả cấu trúc attestation và cách liên kết subject với predicate.
- SLSA đưa ra yêu cầu và mức bảo đảm cho chuỗi cung ứng, trong đó có provenance.
- Chữ ký bảo vệ tính toàn vẹn và xác thực nguồn phát hành attestation.
- Policy của tổ chức quyết định builder, source và quy trình nào được chấp nhận.

Không nên tự gắn nhãn một build đạt một mức SLSA chỉ vì đã tạo file provenance. Mức bảo đảm phụ thuộc việc đáp ứng các yêu cầu cụ thể của phiên bản tiêu chuẩn, bao gồm cách kiểm soát builder và build process.

## 4. Ví dụ cấu trúc provenance

Một in-toto Statement có thể dùng predicate provenance của SLSA. Ví dụ rút gọn sau chỉ minh họa các trường quan trọng; schema đầy đủ và tên trường phải tuân theo phiên bản predicate được khai báo:

~~~json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "registry.example.com/orders/api",
      "digest": {
        "sha256": "7b2d...e91a"
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://example.com/ci/container-build/v1",
      "externalParameters": {
        "sourceRepository": "https://example.com/org/orders-api",
        "sourceRef": "refs/heads/main"
      },
      "resolvedDependencies": [
        {
          "uri": "git+https://example.com/org/orders-api",
          "digest": {
            "gitCommit": "4f9a1c2..."
          }
        },
        {
          "uri": "oci://registry.example.com/base/java",
          "digest": {
            "sha256": "base-image-digest"
          }
        }
      ]
    },
    "runDetails": {
      "builder": {
        "id": "https://ci.example.com/builders/trusted-linux"
      },
      "metadata": {
        "invocationId": "ci-run-1842"
      }
    }
  }
}
~~~

Ví dụ cho thấy subject là artifact được định danh bằng digest; predicate ghi build type, repository, revision, dependency đã resolve và builder. Dữ liệu thực tế cần tuân theo schema, bao gồm các trường bắt buộc và kiểu dữ liệu của phiên bản predicate. Không tự đặt tên trường tùy ý rồi tuyên bố tài liệu tuân thủ SLSA.

externalParameters là đầu vào do bên gọi build cung cấp và cần được kiểm soát theo policy. resolvedDependencies mô tả các dependency hoặc material đã được xác định. builder.id định danh builder thực tế; đây không nên là một chuỗi do job tùy ý khai báo mà không có cơ chế xác minh.

## 5. SBOM là gì?

SBOM là danh mục thành phần phần mềm có trong một sản phẩm hoặc artifact. Nó có thể liệt kê:

- Package và thư viện trực tiếp.
- Dependency gián tiếp (transitive dependency).
- Module, framework và thành phần runtime.
- Phiên bản, nhà cung cấp và định danh package.
- Hash hoặc thông tin xác định thành phần.
- License hoặc thông tin bản quyền.
- Quan hệ phụ thuộc giữa các thành phần.

SBOM giúp đội phát triển, bảo mật và vận hành biết phần mềm đang chứa những gì. Khi một lỗ hổng mới được công bố, tổ chức có thể tìm các artifact có chứa package/version bị ảnh hưởng thay vì dò từng repository bằng tay.

SBOM không tự chứng minh phần mềm an toàn, không thay thế kiểm thử và không đảm bảo mọi dependency đã được phát hiện. Chất lượng SBOM phụ thuộc công cụ, loại artifact, khả năng nhận diện package và thời điểm tạo.

### 5.1. Dependency trực tiếp và gián tiếp

Giả sử ứng dụng khai báo:

~~~text
orders-api
  ├── spring-web
  │    ├── spring-core
  │    └── jackson-databind
  └── postgres-driver
~~~

spring-web và postgres-driver là dependency trực tiếp của ứng dụng. spring-core và jackson-databind là dependency gián tiếp trong ví dụ. Nếu chỉ ghi dependency trực tiếp, SBOM sẽ bỏ sót nhiều package có thể mang lỗ hổng hoặc điều khoản license cần đánh giá.

Một SBOM hữu ích nên phản ánh dependency graph mà công cụ resolve được, bao gồm quan hệ giữa các thành phần. Với container image, cần xem cả package của hệ điều hành, runtime và thư viện ứng dụng nếu công cụ hỗ trợ nhận diện.

### 5.2. Những trường thường gặp

| Trường | Ý nghĩa |
| --- | --- |
| Component name | Tên package hoặc thành phần |
| Version | Phiên bản được phát hiện |
| Package URL (PURL) | Định danh package theo hệ sinh thái |
| Hash | Hash của package hoặc thành phần khi có |
| Supplier/origin | Nhà cung cấp hoặc nguồn package |
| License | License khai báo hoặc phát hiện |
| Relationship | Quan hệ dependency giữa các thành phần |
| Timestamp | Thời điểm tạo SBOM |
| Subject/artifact identity | Artifact mà SBOM mô tả |

Không phải mọi công cụ đều cung cấp đủ tất cả trường. Cần kiểm tra schema, chất lượng dữ liệu và phạm vi quét thay vì chỉ kiểm tra file SBOM có tồn tại.

## 6. Các định dạng SBOM phổ biến

Hai định dạng được sử dụng rộng rãi là SPDX và CycloneDX:

| Định dạng | Trọng tâm | Khi nào phù hợp |
| --- | --- | --- |
| SPDX | Trao đổi thông tin thành phần, license, copyright và quan hệ trong phần mềm | Quản lý license, tuân thủ và inventory |
| CycloneDX | Mô tả BOM cho phần mềm, dịch vụ và các thành phần liên quan đến chuỗi cung ứng | Security analysis, dependency và inventory |

SPDX được chuẩn hóa bởi Linux Foundation và có các phiên bản specification. CycloneDX là tiêu chuẩn BOM của OWASP. Hãy chọn định dạng theo hệ thống tiêu thụ, yêu cầu đối tác và chính sách tổ chức. Một số nền tảng hỗ trợ cả hai.

### 6.1. Ví dụ SBOM CycloneDX rút gọn

~~~json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "metadata": {
    "component": {
      "type": "application",
      "name": "orders-api",
      "version": "1.8.0"
    }
  },
  "components": [
    {
      "type": "library",
      "name": "spring-web",
      "version": "6.1.8",
      "bom-ref": "pkg:maven/org.springframework/spring-web@6.1.8",
      "purl": "pkg:maven/org.springframework/spring-web@6.1.8"
    },
    {
      "type": "library",
      "name": "jackson-databind",
      "version": "2.17.1",
      "bom-ref": "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.17.1",
      "purl": "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.17.1"
    }
  ],
  "dependencies": [
    {
      "ref": "pkg:maven/org.springframework/spring-web@6.1.8",
      "dependsOn": [
        "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.17.1"
      ]
    }
  ]
}
~~~

Đây là ví dụ giản lược để giải thích cấu trúc, không phải SBOM đầy đủ cho một sản phẩm. SBOM thực tế cần các trường bắt buộc theo schema, metadata thời điểm tạo và danh sách thành phần/quan hệ đã phát hiện; serial number là định danh tài liệu hữu ích khi định dạng/phiên bản hỗ trợ. Các giá trị trong dependencies phải tham chiếu đúng bom-ref của component. Hãy validate bằng công cụ hỗ trợ đúng phiên bản CycloneDX trước khi publish.

## 7. Tạo SBOM từ đúng đối tượng cần phát hành

SBOM có thể được tạo từ source tree, dependency graph của package manager, file package hoặc container image. Mỗi cách có phạm vi nhìn thấy khác nhau:

- Tạo từ source hoặc lockfile giúp liệt kê dependency đã khai báo/resolve trong quá trình phát triển.
- Tạo từ binary/package giúp phát hiện những thành phần được đóng gói trong artifact.
- Tạo từ container image giúp bổ sung package của hệ điều hành và runtime trong image.

Với sản phẩm được phát hành dưới dạng container image, nên tạo hoặc kiểm tra SBOM từ chính image đã build. SBOM chỉ được tạo từ source có thể bỏ sót package hệ điều hành hoặc thành phần được thêm trong Dockerfile. Ngược lại, quét image có thể không khôi phục đầy đủ thông tin license hoặc quan hệ dependency đã có trong package manager. Có thể kết hợp nhiều nguồn và hợp nhất theo công cụ phù hợp.

Ví dụ dùng Syft để tạo CycloneDX SBOM cho image:

~~~bash
syft registry.example.com/orders/api:1.8.0 \
  -o cyclonedx-json=orders-api.cdx.json
~~~

Trong pipeline phát hành, nên quét image đã được push và định danh bằng digest thay vì dựa vào tag có thể thay đổi. Cú pháp cụ thể của công cụ có thể thay đổi theo phiên bản; hãy pin phiên bản Syft và kiểm tra output trước khi sử dụng trong pipeline.

Với ứng dụng Java, có thể dùng plugin SBOM của hệ sinh thái build hoặc công cụ quét package. Hãy bảo đảm SBOM bao gồm dependency gián tiếp và khớp với package được đóng gói. Nếu build có shading, repackaging hoặc loại bỏ dependency, cần kiểm tra SBOM phản ánh đúng nội dung cuối cùng.

## 8. Liên kết provenance và SBOM với artifact

Provenance và SBOM trả lời hai câu hỏi khác nhau:

| Bằng chứng | Câu hỏi chính |
| --- | --- |
| Build provenance | Artifact được tạo ở đâu, bởi ai, từ source/materials nào và theo quy trình nào? |
| SBOM | Artifact chứa những thành phần phần mềm nào và chúng liên hệ với nhau ra sao? |
| Vulnerability scan | Những thành phần đã biết có vấn đề bảo mật nào theo dữ liệu tại thời điểm quét? |
| Signature | Nội dung artifact hoặc attestation có bị thay đổi và nguồn ký có được xác thực không? |

Các dữ liệu này nên liên kết bằng digest của artifact. Một SBOM không phải lúc nào cũng có trường chuẩn riêng để chứa digest của toàn bộ artifact; có thể liên kết nó bằng attestation có subject là artifact digest và predicate chứa SBOM, hoặc bằng metadata ngoài được quản lý cùng release. Ví dụ, một release có thể có:

~~~text
orders-api@sha256:7b2d...e91a
  ├── provenance.intoto.jsonl
  ├── sbom.cdx.json
  ├── vulnerability-report.json
  ├── signature / attestation
  └── deployment-record
~~~

Khi artifact được promote từ staging lên production, giữ nguyên digest và các bằng chứng gắn với digest đó. Nếu build lại, dù source commit giống nhau, artifact digest có thể khác do timestamp, toolchain, dependency hoặc yếu tố môi trường. Khi đó phải tạo provenance và SBOM mới cho artifact mới.

Không gắn SBOM của bản build trước vào artifact mới chỉ vì version string giống nhau. Một SBOM phải mô tả đúng đối tượng mà nó tuyên bố.

## 9. Tích hợp provenance và SBOM vào pipeline

Một pipeline điển hình có thể tổ chức theo thứ tự:

1. **Checkout:** lấy đúng commit SHA và ghi nhận repository/ref.
2. **Resolve dependencies:** sử dụng lockfile, repository đã cấu hình và cơ chế verification.
3. **Build và test:** chạy build/test/quality gate trên commit đó.
4. **Package:** tạo artifact bất biến và tính digest.
5. **Generate SBOM:** phân tích artifact cuối cùng hoặc image đã publish, ghi định dạng và phiên bản schema.
6. **Generate provenance:** ghi builder identity, workflow, source revision, materials và build invocation.
7. **Attest/sign:** ký hoặc phát hành attestation bằng danh tính workload tin cậy, ưu tiên credential ngắn hạn.
8. **Publish:** lưu artifact, SBOM và attestation trong registry/kho lưu trữ có kiểm soát.
9. **Verify:** kiểm tra digest, chữ ký, builder, source, policy và SBOM trước khi promote.
10. **Deploy:** triển khai đúng digest đã được xác minh; ghi release/deployment ID.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Git commit đã xác định"] --> B["Resolve dependency và verification"]
    B --> C["Build, test và quality gates"]
    C --> D["Tạo artifact bất biến"]
    D --> E["Tính digest"]
    E --> F["Tạo SBOM từ artifact"]
    E --> G["Tạo build provenance"]
    F --> H["Attest và ký bằng builder identity"]
    G --> H
    H --> I["Publish artifact + SBOM + attestations"]
    I --> J["Verify digest, signature và policy"]
    J --> K{"Đủ điều kiện phát hành?"}
    K -- "Không" --> L["Chặn promote và lưu bằng chứng"]
    K -- "Có" --> M["Promote cùng digest"]
    M --> N["Ghi deployment và release record"]
~~~

Nếu SBOM hoặc provenance không tạo được, cần quyết định rõ đây là điều kiện bắt buộc hay cảnh báo theo policy. Với artifact production quan trọng, tổ chức có thể yêu cầu cả hai phải có và xác minh được trước khi phát hành. Không được âm thầm bỏ qua bước chỉ vì công cụ sinh metadata lỗi.

### 9.1. Ví dụ pipeline trung lập với nền tảng

Đoạn dưới đây minh họa các bước logic, không phải cú pháp của một sản phẩm CI cụ thể:

~~~yaml
pipeline:
  source:
    checkout: exact_commit_sha

  build:
    steps:
      - resolve: locked_dependencies
      - verify: dependency_checksums
      - run: unit_and_integration_tests
      - run: quality_gates
      - package: immutable_artifact
      - calculate: sha256_digest

  evidence:
    steps:
      - generate: sbom_from_final_artifact
      - generate: provenance_from_trusted_builder
      - attest: artifact_digest_and_evidence
      - sign: with_short_lived_workload_identity

  publish:
    steps:
      - upload: artifact_by_digest
      - upload: sbom_and_attestations

  release:
    steps:
      - verify: signature_builder_source_and_policy
      - verify: sbom_and_vulnerability_policy
      - promote: same_artifact_digest
      - record: deployment_identity_and_result
~~~

Tách bước build, evidence, publish và release giúp pipeline dễ kiểm tra. Trong triển khai thực tế, có thể gộp hoặc tách job tùy nền tảng, nhưng cần giữ quan hệ phụ thuộc để không publish hoặc promote artifact chưa có bằng chứng cần thiết.

## 10. Xác minh provenance trước khi triển khai

Người tiêu thụ artifact cần có policy xác định builder và source nào được phép. Ví dụ, chỉ chấp nhận artifact nếu:

- Digest được xác minh khớp với artifact đang triển khai.
- Attestation có chữ ký hợp lệ và chain of trust được chấp nhận.
- Issuer là hệ thống CI/workload identity được tin cậy.
- Repository source nằm trong danh sách được phép.
- Revision là commit đã được review/merge theo chính sách.
- Workflow hoặc build type đúng với pipeline phát hành chuẩn.
- Builder không phải runner tùy ý do người dùng không tin cậy kiểm soát.
- Materials và dependency đáp ứng quy tắc tổ chức.
- SBOM có định dạng hợp lệ, mô tả đúng digest và được tạo trong thời gian phù hợp.

Một chữ ký hợp lệ nhưng đến từ builder không được phép không đủ điều kiện. Một provenance hợp lệ nhưng trỏ đến branch không được phát hành cũng không đủ điều kiện. Xác minh phải kiểm tra nội dung claim lẫn danh tính phát hành.

Có thể dùng policy-as-code để mô tả điều kiện. Ví dụ pseudo-policy:

~~~text
allow deployment only if:
  artifact.digest == attestation.subject.digest
  signature.valid == true
  signer.identity in trusted_builders
  provenance.source.repository in approved_repositories
  provenance.source.revision is approved_revision
  provenance.build_type in approved_build_types
  sbom.subject_digest == artifact.digest
  sbom.schema is supported
  vulnerability_policy == passed
~~~

Đây là logic minh họa. Hệ thống thực tế cần kiểm tra schema, chữ ký, trust root, issuer, subject digest và từng trường theo chuẩn attestation đang dùng.

## 11. SBOM hỗ trợ quản lý lỗ hổng và license như thế nào?

SBOM là đầu vào cho các hoạt động quản trị rủi ro:

- Đối chiếu package/version với cơ sở dữ liệu lỗ hổng.
- Tìm artifact bị ảnh hưởng khi một CVE mới xuất hiện.
- Theo dõi dependency hết hỗ trợ hoặc có license cần xem xét.
- Phân tích thành phần trực tiếp và gián tiếp.
- Hỗ trợ điều tra sự cố chuỗi cung ứng.
- Chuẩn bị dữ liệu cho kiểm toán và yêu cầu của khách hàng.

Kết quả vulnerability scan phải ghi thời điểm quét và nguồn dữ liệu vulnerability. Một SBOM được tạo hôm nay có thể được quét lại ngày mai khi cơ sở dữ liệu CVE cập nhật mà không cần build lại artifact. Vì vậy, hãy phân biệt:

- SBOM: thành phần nào có trong artifact.
- Scan result: thành phần nào có vấn đề theo dữ liệu và policy tại thời điểm quét.
- Exception/risk decision: finding nào được chấp nhận tạm thời và vì sao.

Một SBOM không có finding không đồng nghĩa không có lỗ hổng. Có thể package chưa được nhận diện, phiên bản không rõ, cơ sở dữ liệu chưa có advisory hoặc scanner không hỗ trợ hệ sinh thái đó. Báo cáo cần thể hiện phạm vi và giới hạn phát hiện.

License cũng cần được diễn giải cẩn thận. SBOM có thể ghi license identifier hoặc khai báo của package, nhưng quyết định tuân thủ thường cần đánh giá văn bản license, cách phân phối, sửa đổi và nghĩa vụ pháp lý. Không tự động kết luận một sản phẩm hợp pháp chỉ từ một trường license trong SBOM.

## 12. Bảo vệ provenance, SBOM và thông tin chuỗi cung ứng

Provenance và SBOM giúp tăng minh bạch nhưng cũng có thể tiết lộ thông tin nội bộ:

- Tên repository, project và nhánh.
- Phiên bản dependency và công cụ nội bộ.
- Tên package riêng hoặc registry private.
- Cấu trúc sản phẩm và quan hệ thành phần.
- Địa chỉ dịch vụ, tên môi trường hoặc metadata vận hành.

Các thực hành bảo vệ:

- Không đưa secret, token, private key hoặc credential vào metadata.
- Chỉ công bố SBOM/provenance ở phạm vi người nhận được phép.
- Dùng quyền đọc phù hợp cho registry và kho attestation.
- Ký bằng workload identity hoặc khóa được quản lý, không lưu private key trong repository.
- Ưu tiên credential ngắn hạn và cơ chế cấp quyền theo job.
- Ghi nhận và bảo vệ trust root, certificate và chính sách xác minh.
- Giữ lịch sử attestation bất biến hoặc có audit trail.
- Không để pull request không tin cậy điều khiển builder có quyền ký artifact phát hành.

Với artifact công khai, có thể công bố SBOM và provenance để người dùng xác minh. Với phần mềm nội bộ hoặc sản phẩm có thông tin nhạy cảm, cần chính sách chia sẻ riêng. Tính minh bạch phải đi cùng kiểm soát truy cập.

## 13. Reproducible build và provenance có gì khác nhau?

Hai khái niệm hỗ trợ nhau nhưng không thay thế nhau:

| Khái niệm | Mục tiêu |
| --- | --- |
| Reproducible build | Cùng source và điều kiện build xác định có thể tạo ra artifact giống hệt hoặc tương đương theo tiêu chí đã định |
| Build provenance | Ghi lại artifact được tạo ra từ đâu, bằng builder nào, từ materials và quy trình nào |
| SBOM | Mô tả thành phần có trong artifact |
| Attestation/signature | Bảo vệ và xác thực tuyên bố về artifact |

Một build có provenance vẫn có thể không tái lập được nếu môi trường chứa đầu vào không xác định. Một build tái lập được vẫn cần provenance để người tiêu thụ biết ai đã tạo artifact và quy trình nào đã chạy.

Để tăng khả năng tái lập:

- Pin toolchain và dependency.
- Khóa version của base image.
- Chuẩn hóa timezone, locale và timestamp khi công cụ hỗ trợ.
- Tránh phụ thuộc vào dữ liệu mạng không được kiểm soát.
- Khai báo đầy đủ input/output của task.
- Ghi lại build parameters và materials.

Không nên tuyên bố build reproducible chỉ vì hai lần build có cùng version string. Cần so sánh digest hoặc dùng tiêu chí tương đương đã định nghĩa.

## 14. Các lỗi thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Dùng tag thay cho digest khi xác minh | Tag có thể trỏ sang nội dung khác | Gắn provenance, SBOM và deployment với digest |
| Provenance chỉ ghi tên branch | Không xác định được source revision chính xác | Ghi commit SHA và materials đã resolve |
| Tin mọi chữ ký hợp lệ | Builder không được phép vẫn có thể ký | Kiểm tra issuer, identity, workflow và policy |
| SBOM chỉ liệt kê dependency trực tiếp | Bỏ sót dependency gián tiếp | Xuất dependency graph đầy đủ theo khả năng công cụ |
| Tạo SBOM từ source nhưng phát hành container | Bỏ sót package hệ điều hành hoặc runtime trong image | Quét artifact/image cuối cùng và kết hợp nguồn khi cần |
| SBOM không gắn với artifact cụ thể | Có thể dùng nhầm SBOM của phiên bản khác | Gắn subject digest và kiểm tra khi publish |
| Xem SBOM sạch là phần mềm an toàn tuyệt đối | Scanner có thể thiếu dữ liệu hoặc không nhận diện package | Kết hợp scan, test, policy và đánh giá rủi ro |
| Ghi secret vào provenance | Lộ credential qua metadata | Loại secret và dùng workload identity |
| Build lại ở production rồi dùng provenance của staging | Artifact thực tế khác artifact đã xác minh | Promote cùng digest đã kiểm tra |
| Tự nhận đạt SLSA chỉ vì có file JSON | Không đáp ứng yêu cầu builder/process | Đánh giá theo đúng phiên bản và yêu cầu SLSA |
| Không giữ lịch sử attestation | Khó điều tra khi artifact hoặc policy thay đổi | Lưu metadata, chữ ký và audit trail theo release |

## 15. Checklist cho artifact có thể truy vết

**Artifact**

- [ ] Artifact có định danh bất biến hoặc digest.
- [ ] Tag/phiên bản dễ đọc liên kết với digest thực tế.
- [ ] Artifact được lưu trong registry/kho có kiểm soát.
- [ ] Các môi trường promote cùng một digest.

**Build provenance**

- [ ] Provenance liên kết với đúng subject digest.
- [ ] Source repository và commit SHA được ghi rõ.
- [ ] Builder identity và build type có thể xác minh.
- [ ] Materials/dependency và tham số quan trọng được ghi nhận.
- [ ] Invocation ID và thời điểm build có thể truy vết.
- [ ] Schema/predicate được khai báo đúng phiên bản.

**SBOM**

- [ ] SBOM được tạo từ artifact hoặc image cuối cùng.
- [ ] Dependency trực tiếp và gián tiếp được liệt kê theo khả năng công cụ.
- [ ] Có version, PURL, hash, license và quan hệ khi công cụ hỗ trợ.
- [ ] Định dạng SPDX hoặc CycloneDX được validate.
- [ ] SBOM gắn với digest của artifact tương ứng.
- [ ] Có timestamp và thông tin công cụ tạo.

**Attestation và xác minh**

- [ ] Attestation được ký hoặc bảo vệ bằng cơ chế tin cậy.
- [ ] Trust root, issuer và signer identity được xác minh.
- [ ] Policy kiểm tra repository, revision, builder và build type.
- [ ] Scan result gắn với đúng artifact và thời điểm quét.
- [ ] Không có secret trong metadata.
- [ ] Có audit trail cho publish, verify và deployment.

## Kết luận

Build provenance và SBOM bổ sung hai góc nhìn cần thiết cho artifact: provenance giải thích artifact được tạo ra như thế nào, còn SBOM cho biết artifact chứa những thành phần nào. Khi cả hai gắn với digest bất biến, được phát hành dưới dạng attestation có chữ ký và được xác minh theo policy, tổ chức có thể truy vết từ source commit đến artifact và deployment.

Không nên xem provenance, chữ ký hoặc SBOM như bằng chứng tuyệt đối rằng phần mềm an toàn. Cần xác minh danh tính builder, source revision, materials, schema, thành phần, vulnerability scan và các cổng chất lượng. Giữ cùng digest xuyên suốt quá trình kiểm thử và phát hành giúp tránh nhầm lẫn giữa các phiên bản, hỗ trợ điều tra sự cố và tạo một chuỗi cung ứng phần mềm có thể kiểm chứng.
