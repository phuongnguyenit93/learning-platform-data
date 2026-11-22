# Kiểm tra lại bản vá bảo mật trên phiên bản JDK đã chọn

Chọn được một phiên bản JDK phù hợp cho dự án **Java Advance Compatibility Migration** chưa đồng nghĩa với việc hệ thống đã an toàn để phát hành. Một ứng dụng có thể chạy trên Java 17 hoặc Java 21, biên dịch đúng `--release`, vượt qua toàn bộ unit test nhưng vẫn sử dụng **bản build JDK đã thiếu các bản vá bảo mật**. Tình huống này đặc biệt nguy hiểm khi đội phát triển ghi cấu hình “Java 21” trong CI nhưng Docker image production vẫn đang dùng bản cập nhật cũ, hoặc khi runtime image do `jlink` tạo nhiều tháng trước không được tái tạo từ JDK mới.

Vì vậy, trước khi đưa phiên bản Java đã chọn vào sản xuất, cần **kiểm tra lại mức bản vá thực tế và mức độ phù hợp của các security advisories**. Quy trình này không dừng ở việc đọc CVE hoặc chạy một lệnh quét: phải xác nhận vendor, version, build, provenance, artifact/container thực tế; đọc thông báo của nhà cung cấp; đánh giá tác động lên ứng dụng; kiểm thử security và compatibility; rồi triển khai, theo dõi và cập nhật liên tục.

Bài học thuộc chương **Phát hành và vận hành**. Các thông tin phiên bản/cadence thay đổi theo thời gian; những ví dụ có nhắc tới năm 2026 là minh họa tại thời điểm biên soạn, **không phải danh sách bản vá mới nhất vĩnh viễn**. Trong mỗi đợt release, luôn đối chiếu trang advisory và release notes của chính nhà cung cấp đang được sử dụng.

## 1. Mục tiêu của việc rà soát security patch

Quy trình này phải trả lời được sáu câu hỏi:

1. **Ta đang chạy JDK nào?** Không chỉ “Java 21”, mà là vendor/distribution, full update version, build, OS/architecture và runtime image cụ thể.
2. **Nhà cung cấp đã phát hành bản vá nào?** Có CPU/CSPU, out-of-cycle update hoặc advisory khẩn cấp sau build đang chạy không?
3. **Lỗ hổng nào liên quan tới ứng dụng?** Xét component bị ảnh hưởng, exposed attack surface, client/server usage, parser/TLS/serialization, JDK tools và runtime capabilities.
4. **Phiên bản dự kiến triển khai đã chứa bản sửa chưa?** Có bằng chứng từ release notes/vendor advisory, không chỉ suy từ tên file?
5. **Bản vá có làm thay đổi hành vi không?** TLS, certificate trust, security properties, cryptography, XML, networking, resource limits, class loading và native libraries có thể bị ảnh hưởng.
6. **Mọi instance thực tế đã được thay bằng runtime được vá chưa?** Bao gồm services, batches, consumers, CI, disaster recovery, container images và các runtime tùy chỉnh.

Nếu một câu chưa có bằng chứng, trạng thái thích hợp có thể là **chưa xác minh**, không phải tự động “đã vá”.

## 2. Phân biệt JDK feature version, update version và build

Một số cách ghi thường gặp:

```text
Java 21
21.0.13
21.0.13+11
21.0.13+11-LTS
OpenJDK Runtime Environment Temurin-21.0.x+build
```

Các chuỗi chỉ minh họa cách thể hiện version/build, không khẳng định mọi vendor đều dùng hậu tố giống nhau.

| Trường | Ý nghĩa | Vì sao quan trọng? |
|---|---|---|
| Feature version | Ví dụ 17, 21, 25. | Xác định dòng Java/API/JVM. |
| Update/security version | Ví dụ 21.0.x. | Xác định bản cập nhật trong một dòng JDK. |
| Build number | Hậu tố `+b` hoặc nhãn vendor. | Phân biệt các binary của cùng release name. |
| Vendor/distribution | Oracle JDK, Eclipse Temurin, Azul, Amazon Corretto, Red Hat OpenJDK, v.v. | Lịch phát hành, hỗ trợ và backport có thể khác. |
| OS/architecture | Linux x64/aarch64, Windows, macOS. | Bản vá và binary được phân phối theo platform. |
| Image digest/checksum | Nhận diện artifact thực tế. | Tránh nhầm tag container hoặc file tải về. |

**Cảnh báo quan trọng:** một JDK “17.0.x” từ vendor A không thể tự động được coi là hoàn toàn tương đương về tập backport với bản cùng chuỗi số từ vendor B. Cần dùng danh sách security fixes/release notes của đúng distribution.

Ngoài ra, có thể tồn tại nhiều JDK trong cùng pipeline: JVM chạy Gradle/Maven, compiler toolchain, forked test JVM, runtime của service và runtime của batch. Kiểm tra một JDK không chứng minh các JDK khác đã được vá.

## 3. Lịch cập nhật bảo mật không chỉ có bản major

Các bản JDK feature release thường xuất hiện theo nhịp riêng; bản vá trên một dòng JDK được duy trì theo lịch của nhà cung cấp.

Các thuật ngữ quan trọng:

- **CPU (Critical Patch Update):** chu kỳ cập nhật bảo mật định kỳ của Oracle và các nhà cung cấp liên quan, truyền thống vào tháng 1, 4, 7, 10.
- **CSPU (Critical Security Patch Update):** những đợt security-only/out-of-cycle được phát hành xen giữa CPU khi cần. Các cập nhật thường xuyên hơn đã xuất hiện trong năm 2026.
- **PSU (Patch Set Update):** thuật ngữ trong hệ sinh thái Java/Oracle dùng cho nhánh cập nhật gồm các thay đổi rộng hơn security-only trong những giai đoạn/chính sách tương ứng; cách phát hành và ký hiệu cần xem theo release/vendor.
- **Security Alert / emergency update:** thông báo và bản sửa ngoài lịch bình thường khi cần phản ứng nhanh với lỗ hổng đáng chú ý.
- **Maintenance update:** có thể bao gồm sửa lỗi không chỉ liên quan bảo mật; không mặc định nó chứa mọi CVE chỉ vì được phát hành sau.

Theo kế hoạch công bố năm 2026, bên cạnh các CPU định kỳ đã có các CSPU và hướng phát hành bảo mật với tần suất tăng lên. Vì thế, quy tắc “chỉ kiểm tra vào mỗi quý” không còn đủ trong mọi trường hợp.

**Kế hoạch vận hành hợp lý:** có nhịp kiểm tra định kỳ theo lifecycle của vendor **và** một cơ chế xử lý advisory khẩn cấp khi có bản vá ngoài chu kỳ. Ngày phát hành upstream không nhất thiết là ngày binary của vendor đã sẵn sàng trên mọi OS/architecture.

## 4. Bản vá JDK khác bản vá thư viện ứng dụng

Một ứng dụng Java gồm nhiều lớp:

```text
                   Client / Internet / Partners
                              |
                              v
              API Gateway / Load Balancer / TLS
                              |
                              v
                 Java application/framework
               Spring / Jakarta / libraries
                              |
                              v
                      Java runtime (JDK)
               JSSE, JAXP, java.base, JIT, GC...
                              |
                              v
             Container base image / Native libs
                              |
                              v
                 Operating system / Kernel
```

Vì vậy có ít nhất bốn nhóm vá lỗi phải được phân biệt:

| Nhóm | Ví dụ | Cách kiểm chứng |
|---|---|---|
| **JDK/JVM** | JSSE, JAXP, networking, compiler, class libraries. | Vendor security advisory + JDK build. |
| **Third-party Java dependencies** | Spring, Jackson, Netty, logging, JDBC drivers. | Dependency graph, SCA, vendor advisories. |
| **Container/OS/native** | OpenSSL, zlib, glibc, system packages. | OS package inventory, image scanning, distro advisories. |
| **Infrastructure/managed services** | TLS terminator, IdP, database server, message broker. | Service-provider security bulletins và cấu hình. |

Nâng JDK lên bản vá mới nhất **không tự vá** lỗ hổng của một Jackson JAR được bundling trong ứng dụng. Ngược lại, nâng Jackson cũng không sửa CVE nằm trong JSSE của JDK. Một Docker scanner báo CVE của OS package không nhất thiết thuộc Java runtime, nhưng vẫn cần được quản lý.

## 5. Phạm vi kiểm kê phải bao gồm các runtime không thường xuyên xuất hiện

Không dừng ở web service đang chạy:

- API/backend services và Java servlet/application servers.
- Message consumers, stream processors, scheduled batch.
- Command-line jobs, data migration tools, reporting.
- CI runners, Maven/Gradle daemons, integration test containers.
- Plugin hosts và các process Java khởi chạy gián tiếp.
- Image cho vùng dự phòng/DR, hot standby, disaster recovery.
- Serverless/container tasks dùng Java runtime do platform cung cấp.
- Desktop/client components nếu thuộc scope sản phẩm.
- Runtime image tùy chỉnh tạo bằng `jlink`.
- Những tools chạy Java trong image khác ứng dụng, ví dụ build scanner hoặc code generator.

Một tiêu chí kiểu “100% services đã lên JDK 21” thiếu ý nghĩa nếu không rõ mẫu số. Ví dụ **35/35 workloads đã kiểm kê, bao gồm DR và monthly jobs** cụ thể hơn “100% Java”.

Đối với managed runtime mà tổ chức không trực tiếp chọn JDK build, cần lấy bằng chứng từ tài liệu/support matrix và runtime telemetry của platform; không khẳng định mình đã vá chỉ từ cấu hình application `--release`.

## 6. Thu thập định danh JDK từ binary thật

Trên terminal của runtime environment:

```bash
java -version
java --version
```

Lệnh `java --version` có trên JDK 9+, còn `java -version` cũng hữu ích cho Java 8.

Một output minh họa:

```text
openjdk version "21.0.x" 2026-xx-xx
OpenJDK Runtime Environment VendorName (build 21.0.x+build)
OpenJDK 64-Bit Server VM VendorName (build 21.0.x+build, mixed mode)
```

Các placeholder `x` và `VendorName` không phải một release thực. Khi lập bằng chứng, phải lưu output **nguyên văn** thay vì cắt còn “Java 21”.

Có thể xem thêm system properties:

```bash
java -XshowSettings:properties -version
```

Những property đáng lưu:
- `java.version`.
- `java.vendor`.
- `java.vendor.version` nếu vendor công bố.
- `java.runtime.version` và `java.vm.version` khi có.
- `java.home`.
- `os.name`, `os.arch`.
- `java.version.date` trên các JDK hỗ trợ.

**Lưu ý bảo mật:** output của `-XshowSettings:properties` có thể chứa đường dẫn hoặc cấu hình nhạy cảm. Chỉ lưu và chia sẻ trong hệ thống có kiểm soát.

## 7. Xác minh ngay trong process ứng dụng

Một script chạy `java -version` trên host chưa chắc dùng đúng JVM của container, Gradle test worker hay service process. Nên có chẩn đoán nội bộ được bảo vệ:

```java
import java.util.Map;
import java.util.LinkedHashMap;

public final class JdkIdentity {
    public static Map<String, String> snapshot() {
        Map<String, String> data = new LinkedHashMap<>();
        data.put("java.version",
                System.getProperty("java.version"));
        data.put("java.runtime.version",
                System.getProperty("java.runtime.version"));
        data.put("java.vendor",
                System.getProperty("java.vendor"));
        data.put("java.vm.version",
                System.getProperty("java.vm.version"));
        data.put("java.home",
                System.getProperty("java.home"));
        data.put("os.arch",
                System.getProperty("os.arch"));
        return data;
    }
}
```

Đoạn code tương thích cú pháp Java 8+; một số system property có thể null tùy implementation. Để phát hành, log có kiểm soát hoặc đưa vào inventory nội bộ; **không trả `java.home`/đường dẫn server vào public endpoint**.

Trên JDK 9+, có thêm:

```java
System.out.println(Runtime.version());
```

Khi cần kiểm tra process đang chạy và có quyền thích hợp:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
```

`<pid>` là placeholder. `jcmd` cần công cụ/quyền attach phù hợp; `VM.command_line` có thể tiết lộ tham số chứa secrets, nên phải khử nhạy cảm trước khi ghi bằng chứng.

## 8. Kiểm tra file release và checksum

Trên nhiều JDK distributions, file `release` ở gốc installation chứa thông tin như `JAVA_VERSION`, `IMPLEMENTOR`, `OS_ARCH` và `MODULES`.

Ví dụ shell:

```bash
cat "$JAVA_HOME/release"
```

PowerShell:

```powershell
Get-Content -LiteralPath "$env:JAVA_HOME\release"
```

File `release` có giá trị tham khảo nhưng **không phải chứng minh duy nhất** runtime đang chạy. Biến `JAVA_HOME` có thể khác executable thực tế; custom runtime images/vendors có thể có layout riêng.

Khi tải JDK/JRE binary, lưu checksum cùng nguồn phát hành:

```bash
sha256sum downloaded-jdk-archive.tar.gz
```

PowerShell:

```powershell
Get-FileHash -LiteralPath ".\downloaded-jdk.zip" -Algorithm SHA256
```

Đối chiếu digest/checksum hoặc signature theo hướng dẫn chính thức của vendor. Một checksum **chỉ có ích nếu giá trị tham chiếu lấy từ nguồn tin cậy**. Tự tính hash rồi thấy “hash hợp lệ” không chứng minh file không bị thay đổi trên đường phân phối.

## 9. Ba nguồn bằng chứng nên kết hợp

Nên xây dựng một chuỗi:

```text
Vendor official advisory/release notes
                   |
                   v
       Official patched artifact
         signature / checksum
                   |
                   v
        Build/container image
            digest / SBOM
                   |
                   v
      JVM running in production
        version / image digest
                   |
                   v
        Security test + rollout
                   |
                   v
             Closure record
```

Chỉ có link CVE mà không xác định process đang dùng binary nào là chưa đủ. Chỉ có image digest mà không biết image được build từ JDK nào cũng chưa đủ.

Với supply-chain assurance, có thể thu thập thêm attestations, signed release artifacts, SBOM, provenance và artifact registry metadata theo công cụ mà tổ chức đang sử dụng.

## 10. Chọn đúng nguồn thông tin security

Ưu tiên theo thứ tự:

1. **Security advisory và release notes của vendor JDK đang được sử dụng.**
2. **Oracle Java SE Security Alerts / Critical Patch Update advisory** để hiểu thành phần/CVE được công bố, nếu liên quan tới sản phẩm được mô tả.
3. **OpenJDK vulnerability advisories** và issue/fix metadata để theo dõi upstream.
4. **Vendor distribution release notes** (Temurin, Corretto, Azul, Red Hat, Microsoft Build of OpenJDK và những vendor khác) để biết backport/binary thực tế.
5. **NVD/CVE records, OSV hoặc các database phụ trợ** để đối chiếu mô tả, điểm số và ảnh hưởng.
6. **Internal scanner/SBOM inventory** để xác định triển khai thuộc phạm vi nào.

Không thay vendor source bằng một bảng CVE từ công cụ quét thiếu thông tin product/build/OS. Tình trạng “affected/fixed” cần đối chiếu với **đúng sản phẩm và bản build**, nhất là khi vendor có backport fix nhưng giữ một dòng major/update version khác upstream.

Ví dụ mốc thời gian: Oracle công bố CPU tháng 10/2026; Adoptium cũng có các phát hành CSPU ngoài chu kỳ trong năm 2026. Đây là lý do workflow phải kiểm tra **mỗi bản vá được vendor phát hành**, không chỉ xem danh sách LTS versions.

## 11. Đọc một advisory để trả lời câu hỏi có bị ảnh hưởng không

Một hàng advisory thường có:

| Trường | Cần hiểu |
|---|---|
| CVE ID | Định danh lỗ hổng, không phải artifact version. |
| Product/component | Java SE, JSSE, JAXP, AWT, networking, compiler, JGSS, RMI, v.v. |
| Affected versions | Phiên bản sản phẩm bị ảnh hưởng theo phạm vi vendor công bố. |
| CVSS score/vector | Đánh giá tác động và điều kiện khai thác. |
| Attack vector | Network, local, adjacent, physical tùy lỗ hổng. |
| Privileges/user interaction | Điều kiện attacker cần. |
| Fixed release/build | Phải lấy từ bản vá hoặc release notes chính thức. |
| Notes/mitigations | Giới hạn giả định, điều kiện hoặc cách giảm thiểu tạm. |

Đừng chỉ lấy CVSS điểm cao nhất rồi áp một kết luận lên mọi JVM. Cần đánh giá thành phần bị ảnh hưởng có xuất hiện và có thể bị kích hoạt trong workload không. Tuy nhiên, “chưa thấy code dùng component” **không đồng nghĩa không bị ảnh hưởng** nếu library hoặc provider có thể được gọi gián tiếp.

Đặc biệt, những thông báo của Oracle về ảnh hưởng Java SE, GraalVM, JavaFX, hoặc security components có thể thuộc **sản phẩm khác nhau**. Không đọc nhầm một hàng JavaFX thành việc mọi server Java SE đều chịu đúng risk đó.

## 12. Ưu tiên vá theo khả năng bị khai thác và mức ảnh hưởng

Đánh giá rủi ro theo ít nhất:

- Severity/CVSS và đặc tính CVE.
- Phơi bày qua Internet, network hoặc input không tin cậy.
- Có yêu cầu authentication, quyền đặc biệt hoặc tương tác người dùng không?
- Component có khả dụng trong JDK/runtime image hiện tại?
- Đường thực thi có gọi vào tính năng liên quan không?
- Workload có xử lý file/XML/image/archive từ bên ngoài?
- JDK compiler/tooling có chạy trên CI pipeline nhận input không tin cậy?
- Có bằng chứng bị khai thác thực tế hoặc cảnh báo khẩn cấp không?
- Có bản vá từ vendor trên OS/architecture đang dùng chưa?
- Tác động thay đổi default security settings tới khách hàng/đối tác.

Ví dụ giả định:

| Tình huống | Mức ưu tiên định hướng | Cần xác minh |
|---|---|---|
| JSSE/TLS issue trên public API | Cao | Version thực tế, TLS termination, JSSE usage, fix availability. |
| XML parser vulnerability khi nhận XML từ đối tác | Cao | Parser config, đầu vào không tin cậy, đường khai thác. |
| AWT/image processing issue ở server không xử lý ảnh | Phải đánh giá, có thể giảm ưu tiên | JDK modules, transitive processing, file conversion jobs. |
| Compiler/JDK tools vulnerability trên isolated runtime chỉ chạy app | Phải phân biệt build với runtime | CI access, dynamic compilation, tool presence. |
| Lỗ hổng nội bộ khó khai thác nhưng bản vá sẵn có | Vẫn cần kế hoạch vá | Support policy và tránh tồn đọng JDK cũ. |

Đánh giá reachability là một **công cụ sắp xếp ưu tiên**, không phải lý do mặc định để bỏ qua bản vá bảo mật được nhà cung cấp khuyến nghị.

## 13. Không suy “không có CVE” từ tên phiên bản

Một số sai lầm:
- “Đang ở Java 21 nên chắc đủ mới.”
- “Bản JDK tải tuần này nên chắc chứa CPU gần nhất.”
- “Docker tag `21-jre` đã tự cập nhật production.”
- “Vendor A phát hành build tương tự vendor B nên fix coverage chắc giống.”
- “Scanner không báo CVE vì không biết nhận diện JDK embedded.”
- “Bản runtime không chứa `javac` thì mọi CVE compiler đều không liên quan.”
- “NVD chưa cập nhật, vậy bản build không có vấn đề.”

Mỗi kết luận cần xác định sản phẩm, build, thành phần, binary và bằng chứng. **Không có finding từ một công cụ quét không đồng nghĩa với chứng cứ đã được vá.**

## 14. Tạo ma trận JDK security baseline

Ví dụ bảng nội bộ:

| Workload | Vendor | Runtime hiện tại | Build đã duyệt | Evidence | Trạng thái |
|---|---|---|---|---|---|
| order-api | Temurin | 21.0.x+build-A | 21.0.y+build-B | Vendor notes + image digest | Pending rollout. |
| reporting-batch | Corretto | 17.0.x+build-C | 17.0.y+build-D | Vendor release metadata | Pending test. |
| CI generator | Oracle JDK | 21.0.x+build-E | 21.0.y+build-F | Installer checksum | Pending install. |
| DR consumer | Temurin | Unknown | Target-approved build | Runtime inventory missing | Blocked. |

Các giá trị x/y/build-A/B là placeholders; không đại diện cho JDK thực tế. Trong sản xuất, đừng đánh dấu “patched” khi còn **Unknown** ở ô runtime hoặc thiếu bằng chứng từ vendor.

Ma trận nên có thêm OS/architecture, image digest, thời điểm scan, application owner, patch SLA và kế hoạch rollback. Nó là một cách theo dõi, không thay thế security patch process của doanh nghiệp.
## 15. Chốt phiên bản JDK đích theo chính sách hỗ trợ

Trước khi tải bản vá, cần quyết định:
- Dòng Java nào là baseline mà ứng dụng đã kiểm thử: 11, 17, 21, 25 hoặc một phiên bản khác?
- Nhà cung cấp JDK có duy trì **security updates** cho dòng đó trong thời gian sản phẩm cần hỗ trợ không?
- Bản phân phối và license có phù hợp deployment commercial/on-prem/cloud không?
- Có phải dùng một bản vendor-specific build vì runtime native, OS hoặc compliance?
- Các bản build của OS/CPU production đã sẵn sàng chưa?
- Có yêu cầu runtime JDK giống nhau giữa CI, staging, prod và DR không?
- Có môi trường dùng JVM vendor khác, chẳng hạn Java runtime của managed service không?

**LTS không tự động đồng nghĩa được vá vô hạn.** Mỗi vendor có chính sách support và lịch bảo trì riêng; bản Java feature được chỉ định LTS chỉ hữu ích khi tổ chức thật sự nhận và triển khai các security update tương ứng.

Một nhánh Java đã hết vòng đời hỗ trợ ở vendor đang dùng phải được xử lý bằng một trong các phương án có quản trị: chuyển tới dòng còn hỗ trợ, ký hợp đồng extended support nếu phù hợp, hoặc giới hạn rủi ro với kế hoạch loại bỏ cụ thể. Đừng dùng “chưa có CVE báo cáo” làm lý do duy trì một runtime hết support vô thời hạn.

## 16. Xác nhận CVE đã được sửa ở đúng build

Một advisory có thể nêu affected versions và bản vá được đưa vào một update khác. Cần phân biệt:

1. **Issue được công bố:** định danh CVE, affected components và điều kiện khai thác.
2. **Upstream code fix:** commit/issue ID trong OpenJDK hoặc hệ sinh thái liên quan.
3. **Backport:** fix được đưa về nhánh LTS cụ thể.
4. **Vendor build:** binary chính thức chứa backport.
5. **Application deployment:** image/process thực tế đang chạy binary đó.

Không suy tự động từ (2) sang (5).

Một bản ghi triage:

```yaml
advisoryId: "CVE-YYYY-NNNNN"
product: "Java SE"
component: "JSSE"
vendor: "selected-jdk-vendor"
currentBuild: "21.0.x+oldBuild"
fixedBuild: "21.0.y+approvedBuild"
sourceReferences:
  - "vendor security bulletin URL"
  - "vendor release notes URL"
assessment:
  workload: "order-api"
  exposedSurface: "outbound and inbound TLS"
  affected: "pending-verification"
  priority: "high"
verification:
  runtimeVersionEvidence: "pending"
  binaryChecksumEvidence: "pending"
owner: "platform-team"
status: "triage"
```

Đây là **mẫu dữ liệu minh họa**; không dùng placeholder CVE như một advisory thực tế. Khi vendor công bố một bản fix được backport mà version string không tăng như upstream, cần ghi rõ bằng chứng vendor tương ứng.

## 17. Khi scanner báo CVE nhưng vendor nói đã backport

Lỗi nhận diện có thể xảy ra khi scanner dùng logic so phiên bản đơn giản:

```text
Scanner:
  JDK major/minor appears vulnerable

Vendor:
  Backported fix in vendor-specific build
```

Không nên tự động bỏ finding. Hãy:
1. Xác định scanner đang nhận dạng **JDK runtime** hay một package OS có tên gần giống.
2. Lưu vendor, full build/version và binary checksum.
3. Đọc release notes/advisory chính thức chứng minh fix được tích hợp.
4. Kiểm tra scanner rule/plugin database có cập nhật không.
5. Đánh dấu false positive hoặc fixed-by-backport **có bằng chứng** nếu quy trình công ty cho phép.
6. Theo dõi trong các lần scan sau để bảo đảm không có image cũ tái xuất hiện.

Ngược lại, nếu scanner không nhận diện JDK do image rút gọn hoặc custom path, không được tự suy “không có lỗ hổng”. Cần thêm software inventory/provenance và kiểm chứng thủ công với vendor advisory.

## 18. SCA/SBOM phải bao gồm cả runtime và ứng dụng

**Software Composition Analysis (SCA)** thường tập trung vào JAR/third-party libraries. **Software Bill of Materials (SBOM)** giúp ghi thành phần của một artifact hoặc image.

Trong thực tế, nên có hai lớp inventory:

```text
Application SBOM
  - JARs / WARs / application libraries
  - dependency versions / hashes
  - framework, drivers, native bindings

Runtime/container inventory
  - JDK distribution / exact build
  - OS packages / native libraries
  - image digest / base image
  - optional jlink module list
```

Cách scan phụ thuộc scanner: không phải công cụ nào cũng nhìn thấy JDK trong `/opt/java`, `/usr/lib/jvm` hoặc một `jlink` image đặt đường dẫn tùy biến. Hãy kiểm tra **phạm vi và khả năng nhận diện của chính công cụ**.

Có thể sử dụng SBOM theo CycloneDX hoặc SPDX, kèm attestation/provenance theo chuỗi cung ứng của tổ chức. Tuy nhiên, **SBOM chỉ cho biết “có gì”**, không tự chứng minh binary đó đã được vá hay security tests đã pass.

## 19. Tính toàn vẹn của artifact JDK và container image

Khi lấy bản vá:
- Tải từ trang/repository chính thức hoặc artifact registry đã kiểm duyệt.
- Kiểm tra chữ ký/checksum theo vendor hướng dẫn.
- Ghi URL gốc, thời điểm lấy và release metadata.
- Cố định phiên bản update/build của JDK trong build specification.
- Nếu dùng container image, lưu image digest; tag có thể thay đổi theo thời gian.
- Duy trì cache/mirror nội bộ an toàn để build lại khi cần.
- Đừng tải JDK từ trang không rõ nguồn chỉ vì file có tên đúng phiên bản.
- Không copy ngẫu nhiên `lib/modules` từ build khác sang JDK đang chạy.

Ví dụ một Dockerfile chỉ viết:

```dockerfile
FROM some-jdk-vendor:21
```

chưa đủ chứng minh production đang chạy bản patch đã duyệt, vì tag động có thể được publish lại và deployments đang chạy không tự restart để lấy image mới.

Trong CI cần ghi:
- Full base image reference/digest đã resolve.
- JDK build/version bên trong image sau build.
- Image digest đầu ra.
- SBOM/scan artifact.
- Deployment digest thực tế.

**Ví dụ cú pháp pin digest (giá trị giả):**

```dockerfile
FROM example.com/approved/jdk@sha256:<verified-digest>
```

Đây chỉ là mẫu ghi reference; `<verified-digest>` phải được thay bằng SHA-256 digest thật từ registry tin cậy. Không dùng nguyên Dockerfile ví dụ để build.

## 20. Bản vá của host không tự cập nhật JVM trong container

Một lỗi vận hành phổ biến:

```text
VM host:        OS patched today
Container:      JDK image from three months ago
Running pod:    old immutable image digest
```

Cập nhật OS/host/kernel không tự thay Java runtime đã được đóng gói trong image. Ngay cả khi registry đã phát hành tag mới, container đang chạy vẫn dùng image layer cũ cho tới khi được triển khai lại.

Quy trình:
1. Xác định JDK và digest trong image hiện tại.
2. Chọn patched base image được duyệt.
3. Rebuild application image từ base đó.
4. Chạy tests, scan và lưu provenance.
5. Triển khai image digest mới.
6. Kiểm chứng JVM version/digest ở **tất cả process mới**.
7. Kiểm tra không còn instances cũ trong rollout/DR.

Với các runtime Java cài trực tiếp trên host, dùng cơ chế package/installer của vendor và xác nhận process đã restart để nạp runtime mới. Update một file trên disk không nhất thiết đổi JVM đã khởi động trước đó.

## 21. Các image tạo bằng jlink phải được link lại từ JDK đã vá

Một team có thể dùng:

```bash
jdeps --print-module-deps --class-path "libs/*" app.jar
```

và tạo runtime image:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging,java.sql \
  --output runtime-image
```

Nếu JDK đầu vào đã bị thay bởi bản vá mới nhưng **runtime-image cũ không được tạo lại**, production vẫn dùng module code cũ. Việc update JDK ở build machine không tự làm `jlink` image đã phát hành thay đổi.

Các bước bắt buộc:
1. Xác định JDK đầu vào và provenance.
2. Re-link image từ các JMODs của **JDK build đã vá**.
3. Kiểm tra binary `runtime-image/bin/java -version`.
4. Liệt kê modules từ chính image bằng `--list-modules`.
5. Kiểm tra service providers, TLS, locale, charset, native dependencies.
6. Tạo SBOM/attestation của runtime image mới.
7. Test ứng dụng trên image **được đóng gói cuối cùng**, không chỉ trên full JDK.

Lưu ý: module version list không đủ để chứng minh từng CVE fix; cần nối image về đúng JDK binary/vendor release. Các module `jdk.crypto.ec` hoặc `jdk.localedata` có thể cần tùy ứng dụng; không áp danh sách module mẫu cho mọi service.

## 22. Khi JDK được cài qua OS package manager

Linux distribution có thể phân phối OpenJDK dưới dạng OS packages, đôi khi backport security fixes và thay đổi release suffix theo chính sách riêng.

Ví dụ các lệnh inventory, **không phải lệnh tự nâng cấp**:

```bash
java -version
rpm -qa | grep -i openjdk
```

Hoặc trên hệ dùng Debian packages:

```bash
dpkg -l | grep -i openjdk
```

Package names/câu lệnh tùy OS và distribution. Nếu JDK được cài thủ công vào `/opt`, danh sách RPM/DEB có thể không thấy; nếu có nhiều JDK, package manager có thể hiển thị nhiều gói nhưng process đang chạy một binary khác.

Khi vendor/distro backport fix, **không so cứng version upstream** mà kết luận máy vẫn lỗi. Cần đọc advisory của đúng distro, package changelog và installed package version, rồi xác nhận process thực chạy patched binary.

## 23. Thử bản vá trên môi trường giống production

Bản vá JDK có thể thay:
- JSSE/TLS version, cipher preferences, signature algorithms.
- Certificate path/truststore và danh sách CA tin cậy.
- Security properties như disabledAlgorithms.
- JAXP/XML parser constraints hoặc entity expansion limits.
- Networking, HTTP client, DNS/proxy behavior.
- ImageIO/ZIP/serialization và validation logic.
- Native/JNI APIs, platform libraries, font rendering.
- JIT, GC, memory ergonomics hoặc concurrency corner cases.
- Default behavior của JDK tools/code generation.

Do đó, trước khi rollout phải có môi trường test đại diện về:
- JDK vendor/update/build và OS/CPU.
- Container base image, native packages.
- TLS termination/proxy/identity provider.
- Database, message broker, certificate chain.
- Traffic profile, data format và timezone/locale.
- Runtime launch flags và security configuration.

Một test chạy trên developer laptop bằng vendor khác có thể giúp phát hiện lỗi cơ bản nhưng **không thay thế** xác minh trên binary/image đích.

## 24. Ma trận regression tests sau JDK security update

| Kiểm thử | Điều cần xác nhận |
|---|---|
| JVM startup/health | Không có lỗi khởi động, module/provider resolution. |
| TLS inbound | Clients hợp lệ handshake, certificate chain và hostname validation đúng. |
| TLS outbound | Gọi IdP, APIs, DB TLS, SMTP, broker bằng certificate chính xác. |
| Cryptography | Sign/verify, encrypt/decrypt, key storage và algorithm restrictions. |
| XML/JSON/ZIP | Dữ liệu hợp lệ được xử lý; dữ liệu malformed hoặc độc hại bị từ chối. |
| Authentication/authorization | JWT/OIDC/SAML/session và quyền truy cập không bị nới rộng. |
| HTTP/database/messaging | Đường nghiệp vụ, transaction, queue retry, JDBC behavior. |
| File I/O/native | Quyền file, JNI/JNA, encoding, timezone. |
| Scheduled jobs | Batch/jobs hiếm phải được chạy với fixture đại diện. |
| Performance | Latency P95/P99, CPU, GC, memory, throughput. |
| Monitoring/agents | Metrics, tracing, profiler/Java agents không lỗi tương thích. |
| Rollback | Phương án phục hồi chạy được và không phá dữ liệu. |

Điều kiện cần được viết rõ trong CI/release gate. “Unit test xanh” không chứng minh các TLS certificates trong môi trường đối tác vẫn được chấp nhận, và không chứng minh custom runtime chứa đầy đủ providers.

## 25. Kiểm thử TLS sau khi JDK đổi security policy

Bản vá có thể thêm thuật toán vào danh sách bị vô hiệu hóa, siết key length hoặc thay cấu hình certificate path validation. Điều này thường làm lộ **cấu hình yếu đã tồn tại** ở đối tác hoặc server.

Cần test:
1. TLS handshake tới các endpoint quan trọng.
2. Protocol/cipher suite thực tế được thương lượng.
3. Certificate chain, validity, hostname và SAN.
4. Certificate revocation policy khi được yêu cầu.
5. Client certificate/mTLS nếu có.
6. Keystore/truststore được load đúng.
7. Hành vi khi server cung cấp certificate yếu, hết hạn hoặc sai hostname.
8. Mutual compatibility giữa các JDK runtimes khi rollout hỗn hợp.

Ví dụ Java code dùng public HTTPS API:

```java
import javax.net.ssl.HttpsURLConnection;
import java.net.URL;

public class TlsSmokeTest {
    public static void main(String[] args) throws Exception {
        URL target = new URL("https://api.example.test/health");
        HttpsURLConnection connection =
                (HttpsURLConnection) target.openConnection();

        connection.setConnectTimeout(5000);
        connection.setReadTimeout(5000);

        try {
            int code = connection.getResponseCode();
            System.out.println("HTTP status: " + code);
            System.out.println("Cipher suite: "
                    + connection.getCipherSuite());
        } finally {
            connection.disconnect();
        }
    }
}
```

Đây là test minh họa cho một endpoint thử nghiệm. HTTP status 200 không tự chứng minh mọi policy đã đúng: cần thêm negative tests cho certificate invalid/expired và xác nhận hostname verification **không bị tắt**.

Không chữa `SSLHandshakeException` bằng cách cài trust-all manager hoặc disable hostname verification trên production. Phải xác định nguyên nhân: CA chưa được trust, certificate chain thiếu, thuật toán yếu, clock lệch, TLS protocol không còn cho phép, hoặc server cấu hình sai.

## 26. Security properties và sự khác biệt giữa các image

Các JDK có file cấu hình security, thường ở dạng:

```text
<JDK_HOME>/conf/security/java.security
```

Có thể có các property liên quan:
- `jdk.tls.disabledAlgorithms`.
- `jdk.certpath.disabledAlgorithms`.
- `jdk.jar.disabledAlgorithms`.
- Crypto/security provider settings.
- XML parser/JAXP security limits ở vị trí cấu hình tương ứng.

**Không nên copy nguyên file `java.security` từ một JDK cũ sang JDK mới** để “khôi phục chức năng”. Nó có thể ghi đè những thay đổi bảo mật mà patch vừa đưa vào.

Trên JDK có hỗ trợ, có thể xem tổng quan security settings bằng các tùy chọn launcher như:

```bash
java -XshowSettings:security -version
```

Cú pháp chi tiết và khả dụng phụ thuộc JDK; dùng `java -XshowSettings:help` hoặc tài liệu launcher của đúng bản.

Nếu cần override một security property:
1. Chứng minh thật sự cần.
2. Định nghĩa scope hẹp.
3. Đánh giá rủi ro, có owner/security approval.
4. Không dùng override để vô hiệu hóa bản vá.
5. Có ngày hết hạn và test loại bỏ override.

## 27. Truststore và chứng thư gốc có thể thay đổi sau patch

Bản cập nhật JDK đôi khi thay CA certificates hoặc trust policy. Ứng dụng có thể kết nối tới:
- Public HTTPS services.
- Private PKI trong doanh nghiệp.
- Database hoặc broker mTLS.
- OAuth/OIDC discovery/JWKS endpoints.
- Third-party payment/service APIs.

Các điểm cần đối chiếu:
- Truststore đang dùng: JDK default hay custom?
- File truststore có được copy từ image cũ sang image mới không?
- Có intermediate certificates bị thiếu không?
- Certificate chain có thuật toán/key size còn hợp lệ?
- Clock/timezone của environment có chính xác không?
- Có CA bị rút hoặc trust anchors được cập nhật?

Một lệnh kiểm kê certificate store khi có quyền:

```bash
keytool -list -keystore "path/to/truststore.p12" \
  -storetype PKCS12
```

Nếu cần mật khẩu, **không đặt mật khẩu plaintext trực tiếp trên command line hoặc trong tài liệu**. Dùng cơ chế nhập an toàn/secret manager theo tổ chức. Lệnh trên chỉ minh họa; không cần mở hoặc dump toàn bộ certificate store vào ticket.

### 27.1. Chính sách với CA bị loại bỏ

Nếu vendor rút một root CA không còn tin cậy, việc thêm lại nó vào truststore chỉ để tạm làm TLS “xanh” có thể tái mở đường rủi ro. Ưu tiên:
- Sửa certificate chain/server.
- Chuyển sang CA phù hợp và còn đáng tin cậy.
- Phối hợp partner thay chứng thư.
- Nếu bắt buộc có ngoại lệ, yêu cầu phê duyệt, scope và expiry rõ.

## 28. Kiểm tra chữ ký JAR và disabled algorithms

Bản vá có thể siết chính sách thuật toán ký JAR. Một plugin/distribution JAR từng được ký bằng thuật toán yếu có thể bị xem không còn đáp ứng security policy như trước.

Khi cần kiểm tra artifact đã ký:

```bash
jarsigner -verify -verbose -certs signed-library.jar
```

Kết quả cần được hiểu cùng chính sách của JDK hiện tại và chain certificate. Không nên kết luận tính xác thực/chữ ký an toàn chỉ vì lệnh không báo lỗi nghiêm trọng; cần xác nhận signer, trust và algorithm policy.

Nếu phát hiện signer dùng thuật toán đã bị loại:
1. Yêu cầu thư viện/vendor phát hành bản được ký lại.
2. Kiểm tra artifact gốc và supply-chain provenance.
3. Không tự tắt `jdk.jar.disabledAlgorithms` để tiếp tục dùng JAR không đáng tin.
4. Ghi thông tin release/owner và tác động tới runtime/build plugin.
## 29. Xử lý thay đổi parser, serialization và input validation

Một security update có thể thay giới hạn parser hoặc cách xử lý dữ liệu không tin cậy. Điều này thường bị nhầm là “Java update gây lỗi nghiệp vụ” khi code trước đây phụ thuộc hành vi permissive.

Các nhóm cần chú ý:
- XML parsers, XSLT, XPath, DOM/SAX và entity resolution.
- ZIP/JAR processing, decompression và kích thước dữ liệu.
- Object deserialization và library codecs.
- ImageIO khi xử lý hình ảnh từ bên ngoài.
- Character encoding, Unicode normalization và malformed input.
- File path validation, canonicalization và archive extraction.
- Security defaults của JNDI/RMI trong những hệ thống cũ.

Test tối thiểu:
1. Input hợp lệ vẫn xử lý theo contract.
2. Dữ liệu lịch sử đọc được khi sản phẩm còn cam kết hỗ trợ.
3. Input malformed, oversized hoặc không đáng tin bị từ chối đúng cách.
4. Parser không vô tình bật external entity/resource access nguy hiểm.
5. Error handling không gây timeout, tài nguyên tăng không kiểm soát hoặc lộ secrets.
6. Nếu có thay đổi intentional behavior, release notes nội bộ và contract tests được cập nhật có review.

Không khôi phục cấu hình permissive chỉ để test cũ xanh. Cần xác định **test kỳ vọng sai vì hành vi cũ không an toàn** hay bản vá tạo một regression cần báo vendor.

## 30. Kiểm tra kết hợp thư viện JNI, agents và JDK tools

JDK security patch có thể đồng thời thay cách vận hành native libraries, JDK tool classes hoặc các phần liên quan compiler/JIT/serviceability. Những đường ít được kiểm thử thường gặp:
- JNI/JNA libraries phụ thuộc native ABI.
- APM Java agent, instrumentation/bytecode transformation.
- Profiling/debugging/attach tools.
- Annotation processors và dynamic compilation.
- Java management/monitoring agents.
- Native encryption/compression modules.
- Các đường code chỉ hoạt động trên aarch64 hoặc một Linux distribution cụ thể.

Sau khi nâng JDK build, cần chạy smoke/integration tests trên đúng OS/architecture. Một vendor có thể phát hành binary cho nhiều platform ở thời điểm khác nhau; nên xác nhận từng image **có tồn tại và đã được kiểm tra** trước khi rollout.

Nếu một profiler/agent không tương thích với bản JDK mới, hãy nâng agent hoặc thay đổi cách thu thập thông tin theo support matrix. Không nên chặn bản vá bảo mật vô thời hạn chỉ vì một công cụ phụ chưa được cập nhật; cần quyết định rủi ro và phương án tạm phù hợp.

## 31. Kiểm thử security cần có negative cases

Security patch có thể bảo vệ một đường khai thác mà ứng dụng trước đây vô tình cho phép. Các test bảo mật nên xác định cả hành vi phải **bị từ chối**.

| Thành phần | Positive case | Negative case |
|---|---|---|
| TLS client | Certificate hợp lệ/đúng hostname kết nối được. | Certificate sai hostname/hết hạn/bị rút bị từ chối. |
| JWT/OIDC | Token hợp lệ, issuer/audience đúng, scope đủ. | Token sai chữ ký, expired, sai issuer, thiếu scope bị từ chối. |
| XML parser | XML hợp lệ theo schema được xử lý. | Payload vượt limits hoặc cố truy cập entity ngoài ý muốn bị từ chối. |
| Deserializer | Dữ liệu lịch sử hợp lệ đọc được. | Polymorphic type không tin cậy không được tạo đối tượng nguy hiểm. |
| File/archive | Archive hợp lệ được giải nén vào thư mục cho phép. | Path traversal và oversized payload bị chặn. |
| Truststore | Đối tác dùng CA/cert hợp lệ còn kết nối. | Cert thuộc CA không được tin cậy bị từ chối. |
| JAR signature | Artifact được ký đúng chính sách. | Chữ ký/thuật toán không hợp lệ không được chấp nhận. |

Các bài test phải dùng fixtures an toàn trong môi trường được quản lý, không thực hiện khai thác trên hệ thống ngoài quyền sở hữu. Khi test security, đừng tạo một “test exception” bằng cách tắt kiểm tra mặc định rồi để nó lọt vào production config.

## 32. CI/CD: đặt security patch gate ở đâu?

Một pipeline khuyến nghị:

```text
                Patch advisory / trigger
                          |
                          v
                Select vendor build
                          |
                          v
             Verify signature/checksum
                          |
                          v
              Pin JDK & image digest
                          |
                          v
                Rebuild application
                 + jlink if used
                          |
                          v
             Generate inventory / SBOM
                          |
                          v
            SCA + runtime security scan
                          |
                          v
               Unit + integration tests
                          |
                          v
             Security/TLS contract tests
                          |
                          v
             Performance smoke/load tests
                          |
                          v
                Canary rollout
                          |
                          v
            Verify running JVM/build/digest
                          |
                          v
                 Release approval
```

Dự án Maven có thể dùng:

```bash
mvn verify
```

Dự án Gradle có thể dùng:

```bash
./gradlew test
```

Các lệnh trong bài là **hướng dẫn sử dụng cho dự án thích hợp**, không phải yêu cầu chạy chúng trong quá trình tạo tài liệu. Với integration tests, cần dùng task/phase do project định nghĩa và môi trường test thực tế.

Bản vá mới đôi khi không thay API source nhưng ảnh hưởng integration; đừng bỏ toàn bộ test chỉ để rút ngắn thời gian phát hành security update. Có thể tổ chức **fast security gate** và **full regression suite** với mức rủi ro rõ ràng, nhưng quyết định rút gọn phải được phê duyệt.

## 33. Cổng quyết định GO/NO-GO

Trước release cần trả lời:

| Cổng | Điều kiện có thể kiểm chứng | Nếu chưa đạt |
|---|---|---|
| Binary provenance | JDK binary/digest từ nguồn được phê duyệt. | Chặn release hoặc xin xử lý nguồn không tin cậy. |
| Vendor patch status | Build chứa fixes cần thiết theo advisory. | Chọn build khác hoặc ghi blocker. |
| Vulnerability triage | CVEs đã được phân loại theo affected/not affected/mitigated. | Security review và action owner. |
| Test correctness | Các luồng quan trọng không hồi quy. | Sửa lỗi, test lại. |
| Security regression | Negative tests không nới quyền/giảm trust. | Chặn hoặc xử lý theo chính sách security. |
| Operational readiness | Rollout, observability và rollback/forward-fix sẵn sàng. | Chuẩn bị bổ sung. |
| Environment parity | CI, staging, prod, DR đã có kế hoạch cập nhật tương ứng. | Không đánh dấu “hoàn tất toàn hệ thống”. |
| Evidence | Artifact, version, digest, test reports, sign-off được lưu. | Chưa thể closeout. |

Một advisory khẩn cấp có thể đòi xử lý nhanh hơn release quy chuẩn, nhưng không có nghĩa được phép bỏ hoàn toàn tính toàn vẹn nguồn gốc và kiểm thử bảo mật. Hãy quy định **đường phê duyệt khẩn cấp** riêng từ trước, thay vì tự phá checklist khi sự cố xảy ra.

## 34. Rollout theo canary và kiểm chứng bản vá trên process thực

Một lộ trình:

```text
Old runtime image
       |
       v
Patched build in staging
       |
       v
Canary small traffic set
       |
       v
Security & reliability metrics OK?
     /                 \
    No                 Yes
    |                   |
    v                   v
Contain/diagnose     Expand rollout
    |                   |
    v                   v
Mitigate/forward-fix   All instances updated
                        |
                        v
              Verify actual JVM build
                        |
                        v
               Update baseline record
```

Các chỉ số quan sát:
- Startup failures, crash/restart/OOM.
- TLS handshake failures và certificate validation errors.
- HTTP 4xx/5xx, authentication/authorization errors.
- Connection pool health, DB/broker/IdP connectivity.
- CPU, memory, GC, P95/P99 latency.
- Queue lag và scheduled job completion.
- Security detections/scan findings.
- Số workload còn sử dụng image digest cũ.

**Chỉ triển khai container tag mới không đủ.** Cần xác minh actual runtime JDK/digest trên các instance sau rollout, bao gồm autoscaled workers và vùng dự phòng.

## 35. Rollback sau security patch phải được đánh giá riêng

Rollback patch có thể đưa phiên bản JDK **dễ bị tấn công** trở lại production. Vì vậy có hai rủi ro phải cân bằng:

- **Rủi ro chức năng:** bản vá mới gây regression nghiêm trọng.
- **Rủi ro bảo mật:** bản cũ chứa CVE chưa được khắc phục.

Không định nghĩa “rollback an toàn” là vô điều kiện quay về JDK trước patch. Hãy chuẩn bị nhiều phương án:

1. **Forward-fix:** giữ JDK đã vá, sửa ứng dụng/cấu hình gây regression nếu có thể.
2. **Đổi sang patched build được support khác:** nếu vendor cung cấp bản sửa tương đương phù hợp.
3. **Giảm phạm vi/disable feature bị ảnh hưởng:** có thể cô lập đường chức năng trong thời gian sửa mà không mở thêm lỗ hổng.
4. **Tạm rollback có ngoại lệ:** chỉ khi được đánh giá, phê duyệt, có thời hạn, monitoring và biện pháp hạn chế rủi ro.
5. **Rollback deployment data/config:** nếu bản vá vô tình đi kèm thay đổi application state, phải xem khả năng tương thích dữ liệu.

Nếu lỗ hổng đang bị khai thác, việc trở lại bản cũ có thể bị cấm bởi security policy. Kế hoạch nên có **decision tree ưu tiên giữ bản vá** chứ không coi phiên bản cũ là “known good” trong mọi trường hợp.

## 36. Xử lý bản vá khẩn cấp hoặc ngoài chu kỳ

Một playbook phản ứng nhanh:

```text
Vendor advisory/security alert
             |
             v
Determine affected JDKs and assets
             |
             v
Rate exposure and exploitability
             |
             v
Is a trusted fixed build available?
           /      \
         Yes       No
          |         |
          v         v
    Rapid build    Vendor mitigation/
    + test         containment plan
          |         |
          +----+----+
               |
               v
       Security approval/release
               |
               v
       Verify deployed builds
               |
               v
        Re-scan and close
```

Cần xác định trước:
- Ai theo dõi advisories?
- Ai có thể xác định asset bị ảnh hưởng?
- Ai có quyền phê duyệt hotfix?
- Rút gọn test ở mức nào vẫn được phép?
- Nếu vendor chưa có binary cho OS/architecture đang dùng, escalation path là gì?
- Nếu cần mitigation tạm, ai sở hữu expiry?
- Làm sao chứng minh không còn runtime cũ chạy?

Không tự đặt một lời hứa kiểu “mọi CVE sửa trong 24 giờ” nếu chưa có SLO nội bộ; thời hạn phản ứng phải theo mức độ nghiêm trọng, phơi bày và chính sách tổ chức.

## 37. Khi chưa có bản vá chính thức

Có thể xảy ra tình huống:
- Upstream công bố vấn đề nhưng vendor build chưa sẵn sàng.
- Một platform chưa được hỗ trợ hoặc bản cập nhật phải qua kiểm tra của vendor.
- Java LTS branch đang dùng đã hết support.
- Bản fix phát hành nhưng phá một khả năng tương thích bắt buộc.

Các phương án giảm thiểu có thể gồm:
- Chặn hoặc hạn chế input/đường khai thác liên quan.
- Giới hạn network reachability, authentication và least privilege.
- Tắt tính năng không bắt buộc đang phơi bày component dễ bị tấn công.
- Dùng config mitigation **chính thức** được vendor mô tả.
- Tạm cô lập workload, chuyển sang bản build đã được vá của vendor hỗ trợ khác nếu được kiểm thử.
- Tăng monitoring và anomaly detection.
- Ghi exception có owner, mức ảnh hưởng, hết hạn và trigger tái kiểm tra.

Mitigation **không mặc định tương đương patch**. Khi binary chính thức đã sẵn sàng, vẫn phải hoàn tất quy trình update/verify. Không tự phát minh flag “vô hiệu hóa CVE” không được tài liệu hóa.

## 38. Tổ chức một lịch theo dõi bản vá liên tục

Sau đợt nâng lớn, rất dễ rơi vào tình trạng “đã ổn trên Java 21, sẽ giữ nguyên vài năm”. Nhưng bản JDK vẫn cần cập nhật security trong suốt vòng đời.

Một quy trình lặp:
1. Theo dõi vendor security advisories, release notes và kênh thông báo chính thức.
2. Mỗi khi có CPU/CSPU/security alert, đánh giá asset đang dùng.
3. Cập nhật baseline approved JDK build.
4. Tạo patched artifact/image và scan/test.
5. Triển khai theo mức độ ưu tiên và rủi ro.
6. Xác minh runtime thực trên tất cả workloads.
7. Lưu evidence, đóng issue/ticket và điều chỉnh inventory.
8. Kiểm tra lại exception/mitigation còn mở.

Có thể tự động hóa báo cáo định kỳ: số image chưa được vá, asset chưa rõ JDK build, CVEs chưa triage, exceptions quá hạn, kết quả canary. Tuy nhiên, **quyết định applicability/rollback** của các CVE quan trọng vẫn cần chủ sở hữu có chuyên môn đánh giá.

## 39. Mẫu hồ sơ bản vá phát hành

Ví dụ:

```yaml
patchCampaign:
  id: "JAVA-SECURITY-UPDATE-EXAMPLE"
  description: "Verify approved JDK security patch level"
  advisoryWindow: "2026-10"
  owner: "platform-security"
  status: "in-progress"

targetRuntime:
  featureVersion: "21"
  vendor: "approved-distribution"
  approvedBuild: "21.0.x+approvedBuild"
  source: "official-vendor-release-notes"
  artifactDigest: "sha256:replace-with-verified-digest"

scope:
  applications:
    - "order-api"
    - "order-worker"
    - "monthly-report"
  environments:
    - "ci"
    - "staging"
    - "production"
    - "disaster-recovery"

securityAssessment:
  advisoriesReviewed: true
  affectedCves:
    - id: "CVE-YYYY-NNNNN"
      status: "pending-verify"
      component: "JSSE"
  approvedExceptions: []

validation:
  integrity: "pending"
  runtimeVersion: "pending"
  smokeTests: "pending"
  tlsContracts: "pending"
  integrationTests: "pending"
  imageScan: "pending"
  rollout: "pending"

evidence:
  vendorAdvisory: "vendor-url"
  jdkReleaseNotes: "vendor-url"
  ciRun: "ci-link"
  imageDigest: "registry-digest"
  testReport: "report-link"
  deploymentVerification: "runtime-inventory-link"

approvals:
  security: "pending"
  serviceOwner: "pending"
  operations: "pending"
```

Đây là mẫu ghi nhận theo quy trình, không phải file cấu hình JVM. Các giá trị `pending` và placeholders phải được thay bằng bằng chứng thật trước khi đóng issue; không nên đánh dấu `advisoriesReviewed: true` chỉ vì đã mở một đường link.

## 40. Mẫu báo cáo so sánh trước và sau patch

| Hạng mục | Trước | Sau | Bằng chứng |
|---|---|---|---|
| JDK vendor | Vendor A | Vendor A | `java -version` trên process. |
| JDK build | 21.0.x+old | 21.0.y+new | Runtime inventory. |
| Image digest | Digest cũ | Digest đã duyệt | Container registry/deployment. |
| CVE status | Open/pending | Fixed/mitigated với căn cứ | Advisory + vendor notes. |
| TLS handshake | Baseline | Pass/fail theo contract | Integration test. |
| Security tests | Baseline | Pass | CI report. |
| SLO | Baseline | Trong ngân sách | Canary dashboard. |
| Old instances | N instance | 0 trong scope | Deployment inventory. |
| DR/runtime | Chưa nâng | Đã nâng/xác minh | DR verification. |

Không cần cố cập nhật đồng loạt mọi environment trong một deployment duy nhất nếu chiến lược rollout không cho phép, nhưng chỉ đánh dấu hoàn tất khi đã đạt **phạm vi được phê duyệt** hoặc đã công khai ngoại lệ.

## 41. Sai lầm thường gặp

**“Đã dùng Java LTS nên không cần theo dõi CVE.”** LTS chỉ hữu ích khi tiếp tục nhận và triển khai security updates.

**“Java 21 là bản vá mới nhất.”** Số major không thể hiện patch level; cần full update/build.

**“Oracle có CPU nên mọi vendor có binary cùng ngày.”** Lịch release upstream và binary build/test của vendor có thể lệch; cần xác nhận release thực tế.

**“Scanner xanh nghĩa là JDK đã an toàn.”** Scanner có thể không nhận diện embedded/custom runtime hoặc vendor backports.

**“Scanner báo CVE chắc chắn vẫn tồn tại.”** Có thể là rule chưa biết backport; cần bằng chứng release notes/vendor và chính sách xử lý false positive.

**“Đã cập nhật host thì container JVM cũng được vá.”** Immutable image cũ vẫn chứa runtime cũ cho tới khi rebuild/redeploy.

**“Đã update JDK build machine thì jlink image tự mới.”** Custom runtime phải được re-link và phát hành lại.

**“Bản vá chỉ liên quan bảo mật, không cần regression tests.”** Security defaults, certificate trust và parser behavior có thể thay đổi.

**“Nếu TLS không hoạt động, tắt hostname verification cho nhanh.”** Tạo lỗi bảo mật nghiêm trọng, không phải migration an toàn.

**“Rollback về bản JDK cũ luôn là lựa chọn an toàn.”** Bản cũ có thể chứa lỗ hổng đang bị khai thác; phải đánh giá rủi ro và ưu tiên patched forward-fix.

**“Chỉ cần vá production chính.”** DR, batch, sidecar, CI tools và jobs hiếm vẫn là tài sản có rủi ro.

**“Đánh dấu fixed chỉ vì đã tạo image mới.”** Phải xác minh binary trong process đang chạy và version/digest thực tế.

## 42. Checklist trước khi phê duyệt bản JDK đã chọn

- [ ] Đã chốt JDK feature version, update version, build và vendor/distribution.
- [ ] Có compatibility/support matrix cho OS/architecture và dòng JDK đích.
- [ ] Đã đối chiếu vendor security advisories và release notes mới nhất tại ngày review.
- [ ] Không chỉ dựa vào lịch CPU quý; đã tính CSPU/alerts ngoài chu kỳ.
- [ ] Đã phân loại affected/not affected/fixed/mitigated cho những CVE thuộc phạm vi.
- [ ] Đã có bằng chứng backport nếu version string có thể gây false positive.
- [ ] Đã kiểm tra checksum/signature/provenance của binary tải về.
- [ ] Có inventory/runtime evidence cho mọi app, batch, worker, CI và DR trong scope.
- [ ] Đã kiểm tra JDK thật trong process, không chỉ `JAVA_HOME` trên host.
- [ ] Docker images được rebuild và ghi lại digest; không chỉ thay tag.
- [ ] Custom `jlink` images đã được tạo lại từ JDK đã vá.
- [ ] Có SBOM hoặc software inventory cho runtime và application dependencies.
- [ ] Có kết quả security scan và đã giải thích các findings/chưa nhận diện.
- [ ] Đã chạy smoke, unit, integration và negative security tests phù hợp.
- [ ] Đã kiểm tra TLS/PKIX, certificate trust, crypto providers, JAR signatures nếu liên quan.
- [ ] Đã kiểm tra XML/JSON/ZIP/file parsing và các hạn chế input không tin cậy.
- [ ] Đã xác nhận JDBC/messaging/authentication và external integrations.
- [ ] Đã đo performance/GC/memory và các SLO quan trọng.
- [ ] Có canary rollout, monitoring và đường forward-fix/rollback được duyệt.
- [ ] Không dùng trust-all TLS, disabled security policies hoặc workaround không kiểm soát.
- [ ] Đã xác nhận toàn bộ instance/deployment trong scope chạy đúng build/digest.
- [ ] Các ngoại lệ còn mở có owner, hạn xử lý và biện pháp giảm thiểu.
- [ ] Đã lưu advisory links, build outputs, image digests, test evidence và sign-off.
- [ ] Có quy trình kiểm tra lại patch level cho những bản cập nhật sau.

## 43. Tài liệu tham khảo

- [Oracle Security Alerts, Critical Patch Updates and Security Bulletins](https://www.oracle.com/security-alerts/): nguồn advisories chính thức.
- [Oracle Critical Patch Update Advisory — October 2026](https://www.oracle.com/security-alerts/cpuoct2026.html): ví dụ cách đọc Java SE risk matrix, affected products/versions và CVE metadata.
- [Oracle Java Security Update Cadence (September 2026)](https://blogs.oracle.com/java/transitioning-java-to-more-frequent-security-updates): thông tin thay đổi hướng phát hành bản vá nhiều hơn nhịp hằng quý.
- [Eclipse Temurin Support and Release Roadmap](https://adoptium.net/support/): lịch release, lifecycle và sự khác nhau giữa thời điểm upstream và binary Temurin.
- [Adoptium Secure Software Development Practices](https://adoptium.net/docs/secure-software): quy trình provenance và SBOM của bản phân phối.
- [OpenJDK Vulnerability Group](https://openjdk.org/groups/vulnerability/): thông tin upstream vulnerability work và advisories.
- [OpenJDK JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220): cơ sở của runtime image và nhu cầu re-link khi patch.
- [Java SE 21 System Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): thông tin `java.version`, `java.vendor` và `java.home`.
- [Java SE 21 java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): tham số `-version`, `-XshowSettings` và diagnostic options.
- [JDK 21 jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): kiểm tra process JVM.
- [JDK 21 jlink](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html): tạo runtime images theo module.
- [JDK 21 keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): kiểm tra keystore/truststore.
- [JDK 21 jarsigner](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html): kiểm tra chữ ký JAR.
- [CycloneDX](https://cyclonedx.org/) và [SPDX](https://spdx.dev/): SBOM formats.
- [NIST National Vulnerability Database](https://nvd.nist.gov/): nguồn thông tin CVE/CVSS bổ trợ; không thay thế advisory của vendor.
- [CVE Program](https://www.cve.org/): thông tin định danh và records CVE.

## Kết luận

**Kiểm tra lại bản vá bảo mật trên phiên bản JDK đã chọn** là bước bắt buộc giữa quyết định nền tảng Java và quyết định phát hành/vận hành. Một sản phẩm dùng Java 17 hay Java 21 vẫn có thể dễ bị tấn công nếu đang chạy **update build cũ**, không có nguồn gốc binary đáng tin, hoặc container/jlink image chưa được rebuild sau bản vá mới.

Cách làm có thể kiểm chứng là: xác định **đúng vendor + full version/build + image digest**, đọc advisories và lịch CPU/CSPU của vendor, đánh giá CVE theo component/risk, xác nhận fix đã nằm trong binary, rồi chạy security/compatibility tests trên runtime sẽ triển khai. Sau canary, phải kiểm tra **process đang chạy** thật sự dùng build đã duyệt, đồng thời lưu evidence, owner, exceptions và kế hoạch cập nhật tiếp theo. Bản vá JDK không phải hoạt động “làm một lần khi migration”; đó là một quy trình vận hành liên tục để giữ hệ thống Java tương thích và an toàn sau khi dự án nâng cấp kết thúc.





