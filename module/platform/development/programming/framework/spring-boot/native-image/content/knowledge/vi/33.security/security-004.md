# SBOM, danh mục thư viện và khả năng tạo báo cáo theo bộ công cụ sử dụng

## Mục tiêu bài học

Một ứng dụng Spring Boot được biên dịch thành **GraalVM Native Image** vẫn phụ thuộc vào thư viện Java, framework, runtime, thư viện hệ điều hành và base image. Khi phát hiện CVE hoặc cần chứng minh nguồn gốc thành phần, nhóm vận hành phải biết chính xác binary và container được tạo từ những dependency nào.

**Software Bill of Materials (SBOM)** là danh mục thành phần phần mềm có cấu trúc, thường chứa tên, phiên bản, định danh package, quan hệ dependency, license và checksum. SBOM giúp kiểm kê, đối chiếu lỗ hổng, kiểm tra license và truy nguyên thay đổi trong chuỗi cung ứng phần mềm.

Không có một SBOM duy nhất bao phủ mọi lớp của quá trình build. Maven/Gradle, Spring Boot executable archive, GraalVM Native Image và container buildpack có thể tạo các báo cáo với phạm vi khác nhau. Cần chọn công cụ dựa trên câu hỏi cần trả lời.

Sau bài học, bạn có thể:

- Phân biệt SBOM của dependency graph, native executable và container image.
- Tạo CycloneDX SBOM bằng Maven và Gradle.
- Lấy SBOM được đóng gói trong Spring Boot executable JAR/WAR.
- Bật, xuất và trích xuất SBOM của GraalVM Native Image khi toolchain hỗ trợ.
- Tạo SBOM cho container image bằng buildpack hoặc Syft.
- Đọc component, version, pURL, CPE, dependency relationship và hash.
- Hiểu giới hạn của SBOM khi quét CVE và đưa báo cáo vào CI/CD.

## 1. SBOM là gì và dùng để làm gì?

### 1.1. SBOM mô tả thành phần của phần mềm

Một SBOM có thể liệt kê:

- **Component:** ứng dụng, thư viện, module, package hệ điều hành hoặc thành phần build.
- **Version:** phiên bản được phân phối hoặc được phát hiện.
- **Package URL (pURL):** định danh package theo hệ sinh thái, ví dụ Maven.
- **CPE:** định danh sản phẩm theo Common Platform Enumeration khi có thể ánh xạ.
- **License:** license khai báo hoặc được công cụ phát hiện.
- **Hashes:** checksum để đối chiếu tính toàn vẹn.
- **Dependencies:** quan hệ giữa component và các component mà nó phụ thuộc.
- **Metadata:** thời điểm tạo, công cụ tạo, tên/version của ứng dụng và thông tin build.

Ví dụ một component Maven có thể được nhận diện bằng:

```text
group:    org.springframework
name:     spring-context
version:  6.x.y
pURL:     pkg:maven/org.springframework/spring-context@6.x.y
```

Giá trị 6.x.y chỉ minh họa cấu trúc. SBOM thực tế phải ghi đúng phiên bản đã resolve và đưa vào artifact.

### 1.2. SBOM hỗ trợ những công việc nào?

| Công việc | SBOM cung cấp thông tin |
|---|---|
| Vulnerability management | Component/version để đối chiếu CVE và advisory |
| License compliance | License khai báo/phát hiện của dependency |
| Incident response | Tìm artifact đang chứa một thư viện bị ảnh hưởng |
| Dependency governance | Nhận diện thư viện cũ, trùng lặp hoặc không được phê duyệt |
| Supply-chain traceability | Liên hệ artifact với version, build và dependency graph |
| Release inventory | Lưu danh mục thành phần của từng bản phát hành |

SBOM là dữ liệu đầu vào cho các hoạt động trên. Bản thân SBOM không chứng minh rằng phần mềm an toàn, không có lỗ hổng hoặc được build từ nguồn đáng tin cậy.

### 1.3. Phân biệt SBOM với vulnerability report

- **SBOM** trả lời: phần mềm gồm những component nào?
- **Vulnerability scan** trả lời: component/version đó có khớp advisory hoặc CVE đã biết không?
- **Vulnerability triage** trả lời: phát hiện có ảnh hưởng tới sản phẩm và cách triển khai cụ thể không, mức độ ưu tiên xử lý ra sao?
- **Provenance/attestation** trả lời: artifact được tạo từ source, builder và quy trình nào; dữ liệu đó có được ký/xác minh không?

Một SBOM không thay thế scanner. Scanner cũng không thể phát hiện dependency bị thiếu khỏi SBOM. Muốn đánh giá đúng, phải kiểm tra cả độ đầy đủ của inventory và chất lượng dữ liệu lỗ hổng.

## 2. Các định dạng và phạm vi báo cáo

### 2.1. CycloneDX

CycloneDX là định dạng SBOM được Native Image và nhiều plugin Maven/Gradle hỗ trợ. JSON và XML là hai dạng trao đổi thường gặp. SBOM CycloneDX có thể mô tả component, dependency, license, hash, pURL và các thuộc tính liên quan.

GraalVM Native Image hiện hỗ trợ CycloneDX cho SBOM được tạo trực tiếp bởi Native Image. Các plugin CycloneDX cho Maven/Gradle cũng tạo báo cáo theo định dạng này.

### 2.2. SPDX

SPDX là một chuẩn SBOM khác, thường được dùng trong kiểm kê component và license compliance. Một số công cụ quét container/buildpack có thể xuất SPDX JSON. Native Image SBOM generator không mặc định xuất SPDX; nếu tổ chức yêu cầu SPDX, có thể dùng công cụ khác hỗ trợ định dạng đó hoặc chuyển đổi theo quy trình đã kiểm chứng.

### 2.3. Syft JSON và định dạng riêng của công cụ

Syft có định dạng JSON riêng để giữ các trường package metadata do Syft thu thập. Paketo cũng từng cung cấp schema riêng, nhưng tài liệu hiện tại đánh dấu định dạng Paketo-specific là deprecated; các định dạng Syft, SPDX và CycloneDX JSON là lựa chọn chính.

Không đổi đuôi file từ .cdx.json sang .spdx.json để giả định đã chuyển định dạng. Phải dùng exporter hoặc converter thực sự tạo schema đích.

### 2.4. Mỗi lớp tạo SBOM trả lời một câu hỏi khác nhau

| Nguồn SBOM | Phạm vi điển hình | Câu hỏi phù hợp |
|---|---|---|
| Maven/Gradle CycloneDX plugin | Dependency graph đã resolve theo cấu hình/scope của project | Project khai báo và resolve những thư viện nào? |
| Spring Boot executable archive | SBOM được đóng gói cùng JAR/WAR nếu build đã tạo và package nó | Artifact JVM được phân phối mang theo inventory nào? |
| GraalVM Native Image | Component có thể liên kết với mã reachable trong native executable theo metadata mà builder đọc được | Binary native được tạo từ những thư viện nào? |
| Buildpack SBOM | Dependency theo các layer/buildpack và image; có thể tách build-time/launch-time | Container image và quá trình build sử dụng thành phần nào? |
| Syft scan container | Package có thể phát hiện trong filesystem/layers của image | Image cuối chứa package Java và OS nào? |

Các báo cáo có thể khác nhau mà không nhất thiết có lỗi. Dependency graph có thể gồm thư viện không có code reachable trong native executable; native SBOM có thể không liệt kê package hệ điều hành; container SBOM có thể không chứa dependency chỉ dùng ở build time và không còn trong image cuối.

## 3. Tạo CycloneDX SBOM bằng Maven

### 3.1. Dùng cyclonedx-maven-plugin

Spring Boot hiện hướng dẫn dùng cyclonedx-maven-plugin để tạo SBOM. Nếu dự án dùng spring-boot-starter-parent, parent POM có cấu hình plugin sẵn; vẫn cần khai báo plugin/execution theo cách dự án muốn chạy và publish báo cáo.

Ví dụ gắn goal aggregate vào phase package:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.cyclonedx</groupId>
            <artifactId>cyclonedx-maven-plugin</artifactId>
            <executions>
                <execution>
                    <phase>package</phase>
                    <goals>
                        <goal>makeAggregateBom</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Plugin có thể tạo SBOM cho từng module bằng makeBom, hoặc một báo cáo tổng hợp cho Maven reactor bằng makeAggregateBom. Chọn goal phù hợp với cấu trúc multi-module.

### 3.2. Chạy build và tìm output

Ví dụ:

```bash
./mvnw clean package
```

Với cấu hình mặc định phổ biến, plugin tạo các file trong thư mục target:

```text
target/bom.json
target/bom.xml
```

Tên output, schema version, format và thư mục có thể thay đổi theo plugin configuration. Kiểm tra log Maven và cấu hình thực tế trước khi viết bước upload artifact.

### 3.3. Chọn dependency scope

Plugin Maven có thể đưa các scope compile, provided, runtime, system và test vào hoặc loại ra theo cấu hình. Mặc định phổ biến không bao gồm test scope.

Khi tạo SBOM để phân phối production:

- Bao gồm dependency compile/runtime thực sự đi vào artifact.
- Xác định rõ có cần provided/system scope hay không.
- Không trộn dependency test vào SBOM runtime nếu không có mục tiêu riêng.
- Với multi-module, quyết định có cần aggregate BOM của cả reactor không.

Giữ SBOM của build/test riêng nếu tổ chức cần kiểm kê toàn bộ chuỗi cung ứng CI.

### 3.4. Lưu và publish SBOM

Plugin Maven có thể attach BOM như một artifact bổ sung khi install/deploy. Hãy lưu SBOM cùng version ứng dụng và build metadata; không đặt mọi release ghi đè lên một file bom.json duy nhất.

SBOM phải tương ứng chính xác với binary/container được phát hành. Nếu dependency hoặc profile thay đổi sau khi tạo BOM, cần tạo lại SBOM từ đúng build cuối.

## 4. Tạo CycloneDX SBOM bằng Gradle

### 4.1. Áp dụng plugin

Ví dụ với Groovy DSL:

```groovy
plugins {
    id 'org.cyclonedx.bom' version '3.6.1'
}
```

Hoặc Kotlin DSL:

```kotlin
plugins {
    id("org.cyclonedx.bom") version "3.6.1"
}
```

Phiên bản plugin phải tương thích với Gradle wrapper và build JVM của dự án. Plugin 3.x hiện yêu cầu Gradle 8.4 trở lên; hãy kiểm tra bảng compatibility của phiên bản plugin trước khi nâng.

### 4.2. Tạo aggregate SBOM

Chạy từ root project:

```bash
./gradlew cyclonedxBom
```

Với cấu hình mặc định hiện tại, các output thường gồm:

```text
build/reports/cyclonedx/bom.json
build/reports/cyclonedx/bom.xml
build/reports/cyclonedx-direct/bom.json
build/reports/cyclonedx-direct/bom.xml
<subproject>/build/reports/cyclonedx-direct/bom.json
<subproject>/build/reports/cyclonedx-direct/bom.xml
```

cyclonedxBom tạo aggregate SBOM từ các direct SBOM của root project và subproject được bật. cyclonedxDirectBom tạo báo cáo trực tiếp cho từng project. Cách tổ chức này hữu ích với Gradle multi-project.

### 4.3. Chọn configuration đưa vào BOM

SBOM Gradle phụ thuộc configuration được plugin resolve. Kiểm tra include/exclude configuration để không nhầm test dependency, plugin dependency hoặc dependency không thuộc runtime của ứng dụng với thư viện production.

Với ứng dụng native, nên lưu riêng:

- SBOM dependency graph của project.
- SBOM của native executable nếu GraalVM hỗ trợ.
- SBOM của container image cuối.

Không coi aggregate project BOM là bằng chứng rằng mọi component đều được đưa vào native binary.

## 5. Lấy SBOM từ Spring Boot executable JAR/WAR

### 5.1. SBOM được đóng gói trong executable archive

Spring Boot hỗ trợ in SBOM đã được đóng gói trong uber JAR/WAR bằng jarmode tools:

```bash
java -Djarmode=tools -jar target/payment-service.jar sbom
```

Có thể lưu output vào file để đưa vào pipeline:

```bash
java -Djarmode=tools -jar target/payment-service.jar sbom \
  > target/payment-service-archive-sbom.json
```

Lệnh này chỉ in SBOM nếu archive đã có SBOM được đóng gói và phiên bản Spring Boot hỗ trợ jarmode tương ứng. Nó không tự resolve dependency hoặc tạo SBOM mới từ một JAR bất kỳ.

### 5.2. So sánh archive SBOM với build-tool SBOM

Build-tool SBOM được tạo từ dependency resolution của Maven/Gradle. Archive SBOM là dữ liệu được đóng gói trong executable archive. Kiểm tra:

- Cùng project name/version và source revision.
- Cùng dependency versions.
- Có component nào thiếu hoặc có thêm không.
- SBOM được tạo trước hay sau bước repackage.
- Build profile và dependency scope có giống nhau không.

Nếu archive không chứa SBOM, quay lại bước tạo CycloneDX trong build và kiểm tra cách plugin/artifact đóng gói. Không giả định Spring Boot tự động nhúng mọi SBOM do plugin ngoài tạo.

## 6. SBOM của GraalVM Native Image

### 6.1. Điều kiện hỗ trợ

GraalVM Native Image có thể tạo SBOM dựa trên kết quả static analysis, nhưng tính năng SBOM tích hợp hiện chỉ có trong **Oracle GraalVM**. GraalVM Community Edition không cung cấp tính năng này.

Định dạng được hỗ trợ mặc định là CycloneDX. Khi bật, builder mặc định embed SBOM nén vào native executable. Nếu dùng distribution không hỗ trợ, không nên giả định --enable-sbom sẽ tạo báo cáo; hãy dùng Maven/Gradle CycloneDX và công cụ scan artifact/container.

### 6.2. Bật export và classpath SBOM

Ví dụ:

```bash
native-image \
  --enable-sbom=classpath,export \
  -jar target/payment-service.jar
```

SBOM mặc định được embed; classpath thêm file vào classpath tại META-INF/native-image/sbom.json, còn export xuất SBOM JSON thành build artifact. Xem build output để biết file được tạo ở đâu.

Có thể tắt tính năng bằng --enable-sbom=false, nhưng chỉ nên làm khi có lý do rõ ràng và đã bảo đảm pipeline khác vẫn lưu inventory phù hợp.

### 6.3. Trích xuất SBOM từ native executable

Với Native Image Utils Tool:

```bash
$JAVA_HOME/bin/native-image-utils extract-sbom \
  --image-path=target/payment-service
```

Lệnh xuất nội dung SBOM ở định dạng JSON. Đường dẫn binary phải là native executable đã được build với SBOM embedded.

Có thể dùng Syft để trích xuất embedded SBOM:

```bash
syft scan target/payment-service -o cyclonedx-json
```

Syft cũng có thể liệt kê Java libraries được phát hiện trong native executable:

```bash
syft target/payment-service
```

Kiểm tra version Syft và native-image toolchain đang dùng, vì khả năng đọc embedded SBOM phụ thuộc hỗ trợ định dạng của phiên bản.

### 6.4. Native Image SBOM phản ánh điều gì?

Native Image SBOM được tạo bằng cách khôi phục version information có thể quan sát trong external library manifests cho các class được đưa vào native executable. Nó có thể liệt kê component của ứng dụng và third-party libraries có thể liên kết với class/package tương ứng.

Dependency tree trong SBOM được suy ra từ static analysis/call graph của Native Image. Điều này giúp truy nguyên vì sao một component xuất hiện trong binary.

Tuy nhiên, SBOM có thể có **unassociated types**: một số class/interface/annotation không thể ánh xạ tới component. Nếu thư viện chứa class đó có CVE, scanner có thể không nhận diện được component tương ứng. Hãy xem số lượng unassociated types trong build output/security report và xử lý trước khi coi inventory là đầy đủ.

Nếu entry point class của ứng dụng được liên kết với đúng một component, metadata của SBOM có thể ghi component ứng dụng cùng GAV. Nếu ứng dụng được build thành shared library hoặc entry point không thể ánh xạ duy nhất, trường component ứng dụng có thể không xuất hiện. Kiểm tra metadata và coordinates trước khi kết luận SBOM thiếu ứng dụng.

### 6.4.1. Đọc SBOM trong build output và Build Report

Khi tính năng được hỗ trợ và bật, Native Image build output có thể cho biết:

- SBOM có được tạo hay không.
- SBOM được embed, thêm vào classpath hay export.
- Số component được nhận diện và kích thước SBOM embedded.
- Số type không thể liên kết với component.

Build Report có phần SBOM để xem inventory và tải dữ liệu JSON theo định dạng CycloneDX. Nếu không thấy phần này, kiểm tra GraalVM edition/version, build arguments và trạng thái SBOM trong build output.

Build output/Build Report của Native Image mô tả SBOM ở cấp executable. Nó không thay thế SBOM của container base image và các OS packages trong những layer khác.

### 6.5. Cải thiện component mapping cho fat JAR

Với fat/shaded JAR, package/class có thể khó ánh xạ về đúng Maven component. Native Image Maven plugin có thể tạo baseline SBOM bằng cyclonedx-maven-plugin, xác định package nào thuộc component nào để Native Image liên kết chính xác hơn.

Theo tài liệu GraalVM, tích hợp này có từ GraalVM Native Build Tools Maven plugin 0.10.4 và được bật mặc định khi dùng --enable-sbom. Kiểm tra plugin version và log để xác nhận baseline SBOM được tạo.

Đảm bảo project có GAV coordinates và manifest metadata chuẩn. Nếu component không có group/artifact/version rõ ràng, khả năng liên kết class với dependency có thể giảm.

### 6.6. Hash và strict mode

Có thể yêu cầu SBOM bổ sung hash:

```bash
native-image \
  --enable-sbom=hashes,strict \
  -jar target/payment-service.jar
```

hashes thêm SHA-256/SHA-512 cho các component mà toolchain có thể hash. strict làm build thất bại nếu class/component không thể được ánh xạ theo yêu cầu hoặc hash không tạo được.

Hash giúp đối chiếu dependency với nguồn đáng tin cậy, nhưng không tự chứng minh toàn bộ chuỗi cung ứng an toàn. Ví dụ fat JAR được hash như một artifact tổng hợp; hash đó không nhất thiết bằng hash của từng JAR riêng trên Maven Central. Cần so sánh đúng loại artifact.

### 6.7. Class-level metadata

Native Image có tùy chọn class-level metadata để đưa thông tin module, class, interface, record, annotation, constructor, field và method vào SBOM. Dữ liệu này có thể hỗ trợ điều tra CVE chỉ ảnh hưởng một class hoặc method cụ thể.

Đổi lại, SBOM có thể lớn hơn đáng kể. Tài liệu GraalVM cũng nêu giới hạn: Syft không giữ được toàn bộ nested class-level component metadata khi trích xuất. Chỉ bật khi scanner và quy trình xử lý downstream thật sự cần dữ liệu chi tiết này.

## 7. SBOM từ Buildpacks và container image

### 7.1. Buildpack có thể báo cáo các layer khác nhau

Cloud Native Buildpacks có thể tạo SBOM theo các định dạng Syft JSON, SPDX JSON và CycloneDX JSON. Với Paketo, SBOM có thể mô tả dependency của buildpack, application và image layer.

Tải SBOM từ app image:

```bash
pack sbom download payment-service --output-dir build/sbom/paketo
```

Sau đó kiểm tra các file trong thư mục layer SBOM. Các định dạng và layer thực tế phụ thuộc builder/buildpack được dùng.

### 7.2. Phân biệt build-time và launch-time dependency

SBOM lấy từ app image thường tập trung vào launch-time dependencies. Dependency chỉ cần trong lúc build có thể không xuất hiện trong tập SBOM tải từ image cuối.

Với Paketo, có thể yêu cầu xuất SBOM tại build time:

```bash
pack build payment-service \
  --sbom-output-dir build/sbom/paketo-build
```

Kiểm tra các file trong thư mục layers/sbom/build để xem build-time dependencies. Giữ riêng inventory build-time và launch-time vì chúng phục vụ hai mục tiêu bảo mật khác nhau: bảo vệ môi trường build và bảo vệ artifact runtime.

### 7.3. Quét container image cuối bằng Syft

Syft có thể quét image để phát hiện package trong filesystem/layers, gồm Java archives và package hệ điều hành:

```bash
syft registry.example.com/payment-service:1.2.3 \
  -o cyclonedx-json=build/sbom/payment-service-image.cdx.json \
  -o spdx-json=build/sbom/payment-service-image.spdx.json
```

Syft hỗ trợ nhiều nguồn như Docker/OCI image, archive, filesystem và file đơn. Nếu quét image local bằng Docker/Podman, bảo đảm Syft đọc đúng image store hoặc tag đang kiểm tra.

Container SBOM bổ sung package của base image và các layer hệ điều hành mà SBOM Maven/Gradle hoặc native executable không bao phủ.

### 7.4. Không gộp báo cáo khác phạm vi một cách máy móc

Khi tổng hợp SBOM:

- Giữ lại nguồn tạo và timestamp của từng báo cáo.
- Ghi rõ báo cáo mô tả source dependency, native binary hay container image.
- Tránh cộng trùng cùng component chỉ vì nó xuất hiện ở nhiều layer.
- Không bỏ component chỉ vì một báo cáo khác không có nó.
- Giữ build-time dependency tách khỏi launch-time dependency.

Nếu cần một SBOM tổng hợp, dùng công cụ hỗ trợ merge/aggregate và kiểm tra dependency relationship, component identity, version và provenance sau khi merge.

## 8. Quét lỗ hổng từ SBOM

### 8.1. Dùng Grype với native SBOM

Có thể đưa SBOM trích xuất trực tiếp vào Grype:

```bash
native-image-utils extract-sbom \
  --image-path=target/payment-service | grype
```

Hoặc quét file SBOM đã xuất:

```bash
grype sbom:build/sbom/payment-service-native.sbom.json
```

Kiểm tra cú pháp sbom: theo phiên bản Grype đang cài. Kết quả thường bao gồm component, version đang cài, version có bản sửa, advisory/CVE và mức độ nghiêm trọng theo vulnerability database.

### 8.2. Quét image cuối

Có thể quét trực tiếp image:

```bash
grype registry.example.com/payment-service:1.2.3
```

Quét image giúp kiểm tra cả package hệ điều hành và component phát hiện trong filesystem. Quét native SBOM tập trung vào component Java được Native Image nhận diện. Dùng cả hai khi mục tiêu là đánh giá artifact container hoàn chỉnh.

### 8.3. Đọc kết quả và ưu tiên xử lý

Khi có finding:

1. Xác nhận component name/version và pURL/CPE.
2. Kiểm tra advisory, phạm vi phiên bản bị ảnh hưởng và version đã sửa.
3. Xác định component nằm trong native executable, container base layer hay chỉ có ở build time.
4. Kiểm tra ứng dụng có sử dụng code path bị ảnh hưởng hay không, nếu advisory cung cấp điều kiện khai thác cụ thể.
5. Nâng dependency hoặc base image, sau đó build lại và tạo SBOM mới.
6. Quét lại artifact mới và lưu kết quả.

Không chỉ dựa vào severity. Khả năng khai thác, exposure, privilege, network access, mitigation và môi trường triển khai đều ảnh hưởng mức ưu tiên.

### 8.4. SBOM có thể có false positive hoặc bỏ sót

Các nguyên nhân thường gặp:

- Version metadata không đầy đủ hoặc không đọc được.
- Shading/relocation làm mất quan hệ giữa package và artifact gốc.
- Unassociated types không được liên kết tới component.
- CPE/pURL ánh xạ sai hoặc chưa đủ chính xác.
- Scanner database chưa cập nhật advisory mới.
- Component có trong SBOM nhưng không nằm trên code path có thể khai thác.
- Dependency động tải sau khi build không xuất hiện trong inventory build-time.

SBOM đầy đủ hơn giúp giảm điểm mù nhưng không loại bỏ nhu cầu kiểm tra thủ công các finding quan trọng.

## 9. Tích hợp SBOM vào CI/CD

### 9.1. Tạo báo cáo từ cùng một build

Một pipeline nên tạo và lưu:

- Maven/Gradle CycloneDX SBOM.
- Spring Boot archive SBOM nếu artifact có đóng gói.
- Native Image SBOM nếu Oracle GraalVM và toolchain hỗ trợ.
- Container image SBOM.
- Build metadata: source commit, application version, GraalVM/JDK version, plugin version, target OS/architecture và image digest.

Tất cả báo cáo phải gắn với cùng release/build ID. Không dùng SBOM từ lần build trước cho binary mới.

### 9.2. Kiểm tra tính đầy đủ

Có thể đặt điều kiện:

- SBOM file phải tồn tại và parse được.
- Có metadata của ứng dụng và version mong đợi.
- Có component version và pURL khi dữ liệu nguồn hỗ trợ.
- Native Image unassociated type count không vượt ngưỡng chính sách.
- Container SBOM có package của base image.
- Không có component bị cấm hoặc license vi phạm policy.
- Vulnerability scan không có finding vượt ngưỡng chặn release.

Nếu toolchain không hỗ trợ một loại SBOM, ghi rõ lý do và dùng nguồn thay thế có phạm vi phù hợp. Không tạo file rỗng để làm pipeline trông như đã có báo cáo.

### 9.3. Lưu artifact và kiểm soát truy cập

Lưu SBOM như release artifact bất biến cùng binary/image digest. Bảo đảm người điều tra có thể tìm lại SBOM của một version đã phát hành.

SBOM có thể tiết lộ tên thư viện nội bộ, phiên bản framework và cấu trúc dependency. Cấp quyền truy cập phù hợp với chính sách bảo mật; không mặc định mọi SBOM nội bộ đều phải public.

### 9.4. Theo dõi thay đổi giữa các bản phát hành

So sánh SBOM giữa release hiện tại và release trước để tìm:

- Dependency mới hoặc bị loại.
- Version thay đổi.
- License mới hoặc thay đổi.
- Component xuất hiện trong native image nhưng không có trong baseline.
- Package hệ điều hành thay đổi khi nâng base image.

Chênh lệch SBOM là tín hiệu cần review. Một dependency mới có thể hợp lệ, nhưng nên có lý do và owner rõ ràng.

## 10. Ma trận khả năng tạo báo cáo theo công cụ

| Công cụ | Đầu vào | Định dạng/đầu ra | Phạm vi chính | Giới hạn cần nhớ |
|---|---|---|---|---|
| CycloneDX Maven Plugin | Maven project/dependency graph | CycloneDX JSON/XML | Direct/transitive dependencies theo scope | Không phải inventory chính xác của code reachable trong native image |
| CycloneDX Gradle Plugin | Gradle project/configurations | CycloneDX JSON/XML | Direct/aggregate dependency graph | Phải cấu hình đúng project và configurations |
| Spring Boot jarmode tools | Executable JAR/WAR đã đóng gói SBOM | In SBOM archive ra stdout | Inventory được đóng gói trong archive | Không tự tạo SBOM nếu archive chưa có |
| Oracle GraalVM Native Image | Native Image static analysis + library metadata | CycloneDX embedded/classpath/export | Component liên kết với mã reachable | Chỉ Oracle GraalVM; có thể có unassociated types |
| Paketo Buildpacks | Buildpack layers/app image | Syft JSON, SPDX JSON, CycloneDX JSON | Buildpack và app layer; build/launch dependency | Build-time SBOM cần lấy riêng |
| Syft | Binary, image, filesystem, archive | Syft JSON, CycloneDX, SPDX và định dạng hỗ trợ khác | Package phát hiện trong đầu vào | Phụ thuộc cataloger và nguồn scan |
| Grype | SBOM hoặc image | Vulnerability findings | Đối chiếu component với vulnerability database | Không thay thế SBOM và cần triage finding |

## 11. Quy trình thực hành hoàn chỉnh

### Bước 1 — Tạo dependency SBOM

Chọn Maven hoặc Gradle CycloneDX plugin. Tạo aggregate/direct BOM phù hợp và xác nhận output có dependency version đúng.

### Bước 2 — Kiểm tra Spring Boot archive

Nếu build executable JAR/WAR có SBOM, dùng jarmode tools để in báo cáo và so sánh với dependency SBOM.

### Bước 3 — Build native executable

Với Oracle GraalVM, bật SBOM export/classpath theo cấu hình. Kiểm tra build output để biết SBOM đã được embed/export và có bao nhiêu component/unassociated types.

### Bước 4 — Trích xuất native SBOM

Dùng Native Image Utils hoặc Syft để trích xuất CycloneDX JSON. Xác nhận metadata component, dependency relationship và version.

### Bước 5 — Tạo container SBOM

Quét image cuối bằng Syft hoặc tải SBOM từ buildpack. Kiểm tra base OS, shared libraries và package trong các layer.

### Bước 6 — Quét và triage

Dùng Grype hoặc scanner của tổ chức để đối chiếu CVE. Xác định finding thuộc app dependency, native component, OS package hay build-time dependency.

### Bước 7 — Lưu và so sánh release

Gắn mọi SBOM với source revision, build ID và image digest. Lưu báo cáo bất biến, so sánh với release trước và review component thay đổi.

## 12. Ví dụ cấu trúc artifact của một release

Một release có thể lưu báo cáo theo cấu trúc:

```text
release/
  payment-service
  payment-service-image.tar
  metadata/
    build-info.json
    image-digest.txt
  sbom/
    dependencies.cdx.json
    spring-boot-archive-sbom.json
    native-image.sbom.json
    container-image.cdx.json
    container-image.spdx.json
  security/
    native-image-grype.json
    container-grype.json
```

Đây là cấu trúc gợi ý. Chỉ lưu các file thực sự được tạo; ghi tool/version và phạm vi trong metadata hoặc tên artifact để tránh nhầm báo cáo.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có native SBOM | Dùng GraalVM Community Edition hoặc chưa bật tính năng | Xác nhận Oracle GraalVM và --enable-sbom |
| Native SBOM thiếu component | Manifest/GAV metadata thiếu hoặc fat JAR khó ánh xạ | Dùng Native Build Tools Maven baseline SBOM và kiểm tra unassociated types |
| Maven/Gradle SBOM có nhiều dependency hơn native SBOM | Build graph gồm component không có code reachable trong native image | Đối chiếu scope và mục tiêu của từng báo cáo |
| Container SBOM thiếu build tool | Tool chỉ quét image runtime | Xuất build-time SBOM riêng từ buildpack/CI |
| Spring Boot jarmode không tìm thấy SBOM | Archive không chứa SBOM hoặc version không hỗ trợ jarmode | Tạo và package SBOM trước, kiểm tra Spring Boot version |
| Scanner báo CVE không rõ component | pURL/CPE/version không đầy đủ hoặc ánh xạ sai | Kiểm tra metadata và đối chiếu package gốc |
| Không thể so sánh SBOM giữa các release | Thiếu serial/version/source/build metadata | Gắn SBOM với commit, build ID và image digest |
| SBOM hash không khớp | So fat JAR với hash của từng dependency hoặc artifact bị thay đổi | So đúng loại artifact và nguồn tải tin cậy |

## 14. Checklist review SBOM

- SBOM được tạo từ đúng source revision và dependency lock/resolution của release không?
- Đã xác định báo cáo thuộc dependency graph, archive, native executable hay container image chưa?
- Direct và transitive dependencies có được đưa vào đúng scope không?
- Multi-module project có aggregate SBOM phù hợp không?
- Native Image dùng đúng GraalVM edition và version có hỗ trợ SBOM không?
- Build output có unassociated types không, và đã điều tra chưa?
- Component có name, version, pURL và hash khi công cụ hỗ trợ không?
- SBOM container có package hệ điều hành và base image không?
- Build-time dependencies có được kiểm kê riêng khi cần không?
- Vulnerability scanner dùng database cập nhật và kết quả đã được triage chưa?
- SBOM được lưu bất biến cùng binary/image digest và build metadata chưa?
- Đã so sánh component changes với release trước chưa?

### Câu hỏi tự kiểm tra

1. Vì sao dependency SBOM của Maven/Gradle khác SBOM của native executable?
2. Vì sao native SBOM có thể bỏ sót component nếu class không ánh xạ được về GAV?
3. GraalVM Native Image SBOM hỗ trợ định dạng nào và edition nào có tính năng này?
4. Khi nào nên dùng SBOM của container image ngoài SBOM của native executable?
5. Vì sao build-time dependency cần được kiểm kê riêng với launch-time dependency?
6. SBOM khác vulnerability report và provenance như thế nào?
7. Vì sao hash trong SBOM không thay thế chữ ký artifact và build provenance?
8. Làm thế nào để gắn SBOM chính xác với một release đã phát hành?

## Tài liệu tham khảo

- [GraalVM — Software Bill of Materials in Native Image](https://www.graalvm.org/latest/security-guide/native-image/sbom/)
- [GraalVM — Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/)
- [Spring Boot — Generate a CycloneDX SBOM](https://docs.spring.io/spring-boot/how-to/build.html#howto.build.generate-cyclonedx-sbom)
- [CycloneDX Maven Plugin](https://github.com/CycloneDX/cyclonedx-maven-plugin)
- [CycloneDX Gradle Plugin](https://github.com/CycloneDX/cyclonedx-gradle-plugin)
- [Paketo — Access the Software Bill of Materials](https://paketo.io/docs/howto/sbom/)
- [Anchore Syft](https://github.com/anchore/syft)
- [Anchore Grype — Supported Scan Targets](https://oss.anchore.com/docs/guides/vulnerability/scan-targets/)

**Ghi nhớ:** tạo SBOM ở đúng lớp cần kiểm kê. Maven/Gradle mô tả dependency graph; Spring Boot archive lưu inventory được đóng gói; Native Image mô tả component có thể ánh xạ với mã reachable; buildpack/Syft mô tả package trong image cuối. Dùng nhiều nguồn để có bức tranh đầy đủ, kiểm tra unassociated components, quét CVE và lưu từng báo cáo cùng chính xác release đã phát hành.
