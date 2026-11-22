# Phân biệt phiên bản Java SE với bản phân phối và chính sách hỗ trợ JDK

Khi lập kế hoạch nâng cấp Java, cần trả lời ba câu hỏi riêng: hệ thống đang dùng phiên bản nền tảng Java SE nào, đang chạy bản phân phối JDK của nhà cung cấp nào, và nhà cung cấp đó cam kết cập nhật cũng như hỗ trợ đến thời điểm nào. Ba thông tin này liên quan với nhau nhưng không đồng nghĩa.

Ví dụ, hai máy chủ đều báo Java 21 nhưng một máy dùng Eclipse Temurin, máy còn lại dùng Amazon Corretto. Cả hai hướng tới cùng phiên bản nền tảng Java SE, nhưng có thể khác nhà cung cấp, lịch phát hành bản build, cách đóng gói, điều khoản sử dụng, nền tảng được hỗ trợ và thời hạn hỗ trợ. Nếu chỉ ghi “đã nâng lên Java 21”, kế hoạch migration vẫn thiếu thông tin quan trọng để vận hành và bảo trì lâu dài.

## 1. Java SE, JDK và bản phân phối JDK là ba khái niệm khác nhau

### 1.1. Java SE là nền tảng và đặc tả

Java Platform, Standard Edition (Java SE) xác định nền tảng Java tiêu chuẩn mà ứng dụng Java có thể dựa vào. Phạm vi này bao gồm ngôn ngữ Java, máy ảo Java (JVM), các thư viện/API tiêu chuẩn và những quy tắc kỹ thuật liên quan được mô tả trong các đặc tả tương ứng.

Các phiên bản như Java SE 8, 11, 17, 21 hoặc 25 là các feature release của nền tảng. Mỗi feature release có thể bổ sung cú pháp ngôn ngữ, API, khả năng của JVM và công cụ, đồng thời có thể loại bỏ hoặc đánh dấu deprecated một số thành phần theo quy trình phát triển Java.

Java SE trả lời câu hỏi: **nền tảng Java ở mức đặc tả và API tiêu chuẩn nào đang được sử dụng?** Nó không tự trả lời hệ thống đã tải bộ cài từ nhà cung cấp nào hoặc hợp đồng hỗ trợ thương mại kéo dài bao lâu.

### 1.2. JDK là bộ công cụ phát triển và thực thi

Java Development Kit (JDK) là bộ công cụ dùng để phát triển, biên dịch, kiểm tra, đóng gói và chạy ứng dụng Java. Một JDK thường có:

- `java`: khởi chạy ứng dụng trên JVM.
- `javac`: biên dịch mã nguồn Java.
- `javadoc`: tạo tài liệu API.
- `jar`: tạo và thao tác với file JAR.
- Các công cụ chẩn đoán, kiểm tra, quan sát và đóng gói khác, tùy phiên bản và nhà cung cấp.
- Các module thư viện tiêu chuẩn cùng thành phần runtime cần thiết.

JDK là một implementation cụ thể của nền tảng Java. JDK cần cung cấp các hành vi và API theo phạm vi đặc tả mà nó tuyên bố hỗ trợ, đồng thời có thể đi kèm công cụ hoặc tính năng bổ sung của nhà cung cấp.

### 1.3. Bản phân phối JDK là sản phẩm được đóng gói và cung cấp

Bản phân phối JDK (JDK distribution hoặc JDK build) là bộ cài hoặc artifact nhị phân do một tổ chức xây dựng, kiểm thử, đóng gói và phát hành. Nhà cung cấp có thể xây dựng từ mã nguồn OpenJDK, áp dụng các bản vá hoặc cấu hình riêng, rồi cung cấp cho những hệ điều hành và kiến trúc cụ thể.

Một số ví dụ về bản phân phối phổ biến gồm:

- Oracle JDK.
- Eclipse Temurin.
- Amazon Corretto.
- Azul Zulu.
- Microsoft Build of OpenJDK.
- Red Hat build of OpenJDK.

Danh sách này chỉ minh họa các sản phẩm trên thị trường, không phải bảng xếp hạng và cũng không hàm ý các sản phẩm có cùng điều khoản hoặc thời hạn hỗ trợ. Cần kiểm tra thông tin của đúng nhà cung cấp, phiên bản, hệ điều hành và loại gói đang định sử dụng.

OpenJDK là dự án và cơ sở mã nguồn mở của JDK. Một bản build từ mã nguồn OpenJDK vẫn cần được đóng gói, kiểm thử, phát hành và bảo trì bởi một tổ chức hoặc cộng đồng cụ thể. Vì vậy, tên “OpenJDK” trong trao đổi kỹ thuật có thể đang chỉ dự án mã nguồn, một bản build cụ thể hoặc cách gọi chung cho các JDK dựa trên OpenJDK; khi lập kế hoạch hỗ trợ phải ghi rõ nghĩa đang dùng.

## 2. Quan hệ giữa Java SE release và JDK distribution

Có thể hình dung mối quan hệ như sau:

```text
Java SE feature release (ví dụ Java SE 21)
    ├── Đặc tả ngôn ngữ và JVM
    ├── API tiêu chuẩn
    └── Các yêu cầu tương thích của nền tảng
             │
             ▼
JDK implementation / mã nguồn nền tảng
             │
             ├── Nhà cung cấp A xây dựng và kiểm thử
             ├── Nhà cung cấp B xây dựng và kiểm thử
             └── Nhà cung cấp C xây dựng và kiểm thử
                      │
                      ▼
             Các JDK distribution/build
             ├── Gói cài cho Linux, Windows, macOS
             ├── Gói cho x64, AArch64 và kiến trúc được hỗ trợ
             ├── Bản cập nhật và bản vá
             └── Điều khoản, lịch phát hành và hỗ trợ riêng
```

Hai bản phân phối cùng hướng tới Java SE 21 được kỳ vọng tuân theo cùng nền tảng tiêu chuẩn trong phạm vi tương thích mà chúng công bố. Tuy nhiên, chúng không nhất thiết có cùng số build, cùng lịch phát hành, cùng bản vá, cùng cấu hình mặc định hoặc cùng phạm vi hỗ trợ hệ điều hành.

Một nhà cung cấp có thể phát hành bản cập nhật dựa trên mã nguồn upstream mới nhất. Nhà cung cấp khác có thể backport bản vá bảo mật hoặc sửa lỗi vào một nhánh cũ hơn để tiếp tục hỗ trợ khách hàng. Do đó, không thể chỉ so sánh số build hoặc ngày phát hành để kết luận bản nào an toàn hơn hay được hỗ trợ lâu hơn.

## 3. Phân biệt feature release, update release và build number

Java hiện sử dụng chu kỳ feature release thường xuyên. Các feature release tạo ra những mốc nền tảng như Java 17, 21 hoặc 25. Giữa các mốc này, nhà cung cấp phát hành các bản cập nhật để sửa lỗi, xử lý lỗ hổng bảo mật và duy trì chất lượng runtime.

Một chuỗi phiên bản thường gặp là `21.0.2+13`. Có thể đọc ở mức khái quát:

| Thành phần | Ý nghĩa |
|---|---|
| `21` | Feature version, xác định dòng nền tảng Java 21. |
| `0` | Thành phần interim trong quy tắc đánh phiên bản hiện đại; thường giữ giá trị 0 ở các bản phát hành thông dụng. |
| `2` | Update level, biểu thị mức cập nhật trong feature release đó. |
| `+13` | Build number của bản build được phát hành. |

Chuỗi thực tế có thể thêm thông tin như nhãn LTS hoặc metadata do nhà cung cấp sử dụng. Cần đọc theo quy tắc phiên bản của JDK tương ứng, không tự suy ra rằng mọi đoạn số đều có ý nghĩa giống nhau giữa các sản phẩm.

### 3.1. Feature release

Feature release như Java 17 hoặc Java 21 xác định một thế hệ nền tảng. Khi chuyển từ Java 17 lên Java 21, nhóm có thể phải xử lý thay đổi ngôn ngữ, API, JVM, garbage collector, công cụ, framework và dependency. Đây thường là phạm vi migration lớn hơn so với cập nhật patch trong cùng feature release.

### 3.2. Update release

Update release trong cùng feature line thường tập trung vào sửa lỗi, bảo mật, cập nhật dữ liệu timezone, certificate, thư viện và thành phần runtime. Mục tiêu là giữ tương thích trong phạm vi chính sách của feature release, nhưng ứng dụng vẫn cần được kiểm thử vì bản sửa lỗi có thể làm lộ phụ thuộc vào hành vi cũ, thay đổi kết quả ở trường hợp biên hoặc thay đổi thành phần bảo mật.

### 3.3. Build number và metadata của nhà cung cấp

Build number giúp nhận diện một lần build cụ thể. Hai vendor có thể dùng build number khác nhau cho cùng feature/update level vì quy trình build và lịch phát hành khác nhau. Metadata có thể chứa hậu tố riêng, nhãn LTS hoặc thông tin build. Khi ghi nhận sự cố, cần lưu toàn bộ output `java -version` thay vì chỉ ghi số `21`.

## 4. Không nhầm JDK, runtime image và JRE

JDK thường bao gồm runtime cùng công cụ phát triển. Trước đây, nhiều nhà cung cấp phân phối JRE riêng cho việc chạy ứng dụng. Từ Java 9 trở đi, nền tảng module và khả năng tạo runtime image cho phép đóng gói runtime theo nhu cầu; nhiều sản phẩm hiện tập trung phân phối JDK đầy đủ hoặc runtime image tùy chỉnh.

Vì vậy, không nên giả định rằng mọi nhà cung cấp đều cung cấp một gói JRE độc lập cho mọi feature release. Nếu production chỉ cần chạy ứng dụng, tổ chức có thể sử dụng runtime image được tạo bằng `jlink`, một gói runtime do vendor cung cấp hoặc image container đã chứa runtime. Cần xác minh runtime image có đủ module, provider, certificate, locale, timezone data và công cụ chẩn đoán mà ứng dụng cần.

Việc đổi từ JDK đầy đủ sang runtime image tối giản có thể làm mất các công cụ như `jcmd`, `jstack` hoặc `jmap` trong container. Điều này không nhất thiết làm ứng dụng không khởi động, nhưng có thể ảnh hưởng khả năng xử lý sự cố. Đây là một quyết định đóng gói/vận hành cần được kiểm tra riêng.

## 5. LTS là chính sách hỗ trợ, không phải một feature của ngôn ngữ

LTS (Long-Term Support) thường được dùng để chỉ một feature release mà nhà cung cấp hoặc tổ chức phân phối cam kết duy trì trong thời gian dài hơn so với các nhánh phát hành ngắn hạn. Tuy nhiên, nhãn LTS không tự bảo đảm mọi nhà cung cấp có cùng thời gian hỗ trợ, cùng lịch cập nhật hoặc cùng điều kiện sử dụng.

Cần phân biệt:

- **Feature release:** mốc kỹ thuật của nền tảng, ví dụ Java 21.
- **LTS designation:** cách nhà cung cấp hoặc tổ chức phân phối phân loại một dòng phát hành theo chính sách hỗ trợ của họ.
- **Support lifecycle:** thời gian và loại hỗ trợ thực tế mà nhà cung cấp cam kết cho một sản phẩm cụ thể.

Một feature release có thể được nhiều nhà cung cấp phân phối, nhưng mỗi nhà cung cấp có thể công bố mốc kết thúc hỗ trợ khác nhau. Một nhà cung cấp có thể cung cấp cập nhật bảo mật miễn phí trong một khoảng thời gian; một nhà cung cấp khác có thể yêu cầu đăng ký dịch vụ thương mại cho một số loại hỗ trợ hoặc môi trường sử dụng. Điều kiện này cần được xác nhận trong điều khoản hiện hành.

LTS cũng không có nghĩa một phiên bản sẽ được hỗ trợ vô thời hạn. Đến thời điểm kết thúc một giai đoạn hỗ trợ, nhà cung cấp có thể ngừng phát hành bản vá công khai, chuyển sang gói hỗ trợ mở rộng có điều kiện hoặc kết thúc toàn bộ hỗ trợ. Tên các giai đoạn có thể khác nhau theo vendor.

## 6. Những thành phần của chính sách hỗ trợ JDK

Khi đánh giá một bản phân phối, không nên chỉ hỏi “có LTS không?”. Cần đọc chính sách hỗ trợ theo từng nội dung cụ thể.

| Thành phần chính sách | Câu hỏi cần xác nhận |
|---|---|
| Thời hạn hỗ trợ | Ngày bắt đầu, mốc kết thúc cập nhật công khai, kết thúc hỗ trợ tiêu chuẩn và hỗ trợ mở rộng là khi nào? |
| Bản vá bảo mật | Có cung cấp bản vá CVE cho feature line đang dùng không? Tần suất và thời gian xử lý được công bố ra sao? |
| Sửa lỗi | Chỉ nhận bản sửa từ upstream hay vendor có backport cho nhánh cũ? Phạm vi lỗi nào được xử lý? |
| SLA và kênh hỗ trợ | Có hỗ trợ kỹ thuật, thời gian phản hồi, quy trình escalation và hỗ trợ production không? |
| Hệ điều hành/kiến trúc | Có build cho đúng OS, CPU architecture, container base image và môi trường ảo hóa không? |
| Điều khoản sử dụng | Được dùng trong phát triển, kiểm thử, production và phân phối lại theo điều kiện nào? Có giới hạn thương mại không? |
| Tuân thủ và bảo mật | Có yêu cầu hoặc bằng chứng về FIPS, crypto provider, chứng nhận, SBOM hay quy trình xử lý lỗ hổng không? |
| Công cụ và tính năng | Có hỗ trợ các công cụ chẩn đoán, Java Flight Recorder, Mission Control hoặc tính năng cần cho vận hành không? |
| Cập nhật nền tảng | Vendor có duy trì bản build cho phiên bản OS, kiến trúc và môi trường container đang dùng không? |

Một số nhà cung cấp dùng lịch cập nhật theo quý, một số có thể có bản cập nhật bổ sung khi cần. Tên gọi như CPU, PSU, Critical Patch Update hoặc security update là thuật ngữ của từng tổ chức và không nên mặc định chúng có cùng phạm vi. Hãy đọc advisory và release notes của đúng sản phẩm.

## 7. OpenJDK, vendor build và chứng nhận tương thích

OpenJDK cung cấp cơ sở mã nguồn mở để xây dựng JDK. Các nhà cung cấp có thể sử dụng mã nguồn đó để tạo bản build, thêm bản vá, cấu hình build, đóng gói installer và cung cấp hỗ trợ.

Không nên đồng nhất ba việc sau:

1. **Dùng mã nguồn OpenJDK:** cho biết nguồn gốc hoặc nền tảng mã nguồn của implementation.
2. **Phát hành một bản build JDK:** cho biết có một artifact cụ thể được xây dựng, kiểm thử và phân phối.
3. **Tuyên bố tương thích Java SE:** cho biết sản phẩm tuyên bố đáp ứng đặc tả nền tảng và có thể có bằng chứng kiểm thử/chứng nhận tương ứng.

Một sản phẩm có nguồn gốc OpenJDK không tự động có cùng điều khoản hỗ trợ với mọi sản phẩm khác cũng dựa trên OpenJDK. Tương tự, hai sản phẩm cùng feature release không nhất thiết có cùng mức chứng nhận, phạm vi OS/architecture hoặc cam kết dịch vụ.

Khi yêu cầu tương thích chuẩn là bắt buộc, cần kiểm tra tuyên bố tương thích Java SE và chương trình kiểm thử/chứng nhận mà vendor công bố cho đúng phiên bản, thay vì chỉ dựa vào tên “OpenJDK” hoặc kết quả `java -version`.

## 8. Khác biệt giữa các bản phân phối có thể ảnh hưởng migration như thế nào?

Với một ứng dụng Java tiêu chuẩn, chuyển giữa hai bản phân phối cùng feature release và update level thường được kỳ vọng giữ hành vi nền tảng Java SE. Dù vậy, vẫn có các khác biệt có thể ảnh hưởng môi trường thực tế:

- Bản vá riêng hoặc backport của nhà cung cấp.
- Cấu hình mặc định của JVM, GC, memory ergonomics hoặc container awareness.
- Native library, crypto provider, security policy và chứng chỉ CA được đóng gói.
- Dữ liệu timezone, locale, font và thành phần hệ điều hành.
- Hỗ trợ kiến trúc CPU, OS version và container base image.
- Công cụ chẩn đoán, module bổ sung hoặc tính năng riêng của vendor.
- Cách cài đặt, cập nhật, đặt `JAVA_HOME`, ký package và tích hợp với hệ điều hành.

Ví dụ, một ứng dụng kết nối HTTPS có thể hoạt động trên máy phát triển nhưng lỗi trong container do truststore hoặc CA certificate khác nhau. Một ứng dụng phụ thuộc vào provider mã hóa cụ thể có thể không khởi động nếu provider không được đóng gói hoặc cấu hình giống môi trường cũ. Những vấn đề này không nhất thiết là khác biệt của Java SE API; chúng có thể xuất phát từ distribution, OS image hoặc cấu hình triển khai.

Vì vậy, khi đổi vendor hoặc distribution, cần kiểm thử trên chính OS/architecture và container image dự kiến chạy production. Nếu tổ chức sử dụng tính năng riêng của vendor, phải ghi nhận rõ dependency đó và phương án thay thế trước khi chuyển đổi.

## 9. Chọn JDK distribution cho một hệ thống

Không có một bản phân phối phù hợp cho mọi tổ chức. Việc lựa chọn nên dựa trên yêu cầu kỹ thuật, vận hành, pháp lý và hỗ trợ.

### 9.1. Các tiêu chí lựa chọn

**Tương thích nền tảng:** xác nhận feature release, update level, OS, architecture, container và framework được hỗ trợ.

**Chính sách cập nhật:** xác nhận tần suất phát hành, cách nhận bản vá bảo mật, thời gian xử lý lỗ hổng và cách vendor backport sửa lỗi cho feature line cũ.

**Điều khoản và chi phí:** kiểm tra quyền sử dụng trong development, test, staging, production, môi trường cloud và phân phối lại. Đừng suy luận điều khoản từ việc mã nguồn upstream là mã nguồn mở; điều khoản của artifact và dịch vụ hỗ trợ phải được đọc riêng.

**Hỗ trợ vận hành:** xác định có cần SLA, hỗ trợ sự cố production, tư vấn migration, bản vá khẩn cấp hoặc hỗ trợ hệ điều hành dài hạn hay không.

**Yêu cầu bảo mật và tuân thủ:** kiểm tra crypto provider, FIPS nếu có yêu cầu, truststore, SBOM, quy trình xử lý CVE, ký artifact và nguồn tải đáng tin cậy.

**Khả năng chuẩn hóa:** ưu tiên một chính sách rõ ràng cho môi trường local, CI, container và production. Nếu cần nhiều distribution, phải có lý do và ma trận kiểm thử cho từng loại.

### 9.2. Mẫu bảng đánh giá vendor

| Tiêu chí | Vendor/Distribution A | Vendor/Distribution B | Bằng chứng cần lưu |
|---|---|---|---|
| Feature release |  |  | Phiên bản JDK và release notes |
| Update level |  |  | Output version và advisory |
| OS/architecture |  |  | Ma trận nền tảng được hỗ trợ |
| Security updates |  |  | Lịch cập nhật và chính sách CVE |
| Support end date |  |  | Lifecycle chính thức của sản phẩm |
| License/terms |  |  | Điều khoản sử dụng hiện hành |
| Commercial SLA |  |  | Hợp đồng hoặc trang dịch vụ hỗ trợ |
| Runtime/tooling |  |  | Danh sách công cụ, module và tính năng cần thiết |
| Container support |  |  | Base image, digest, OS packages và architecture |
| Compliance needs |  |  | Chứng nhận hoặc tài liệu kỹ thuật được yêu cầu |

Không nên điền ngày kết thúc hỗ trợ bằng một con số chung cho “Java 21”. Phải ghi đúng sản phẩm, vendor, loại hỗ trợ, phiên bản OS và điều kiện hợp đồng tương ứng.

## 10. Xác định JDK thực tế trong môi trường build và runtime

Một dự án có thể sử dụng nhiều JDK trong cùng một pipeline:

- JDK chạy Gradle daemon hoặc Maven.
- JDK toolchain dùng để biên dịch và chạy test.
- JDK mục tiêu được tạo bytecode và API tương thích.
- JDK trong container hoặc máy chủ production.
- JDK dùng trong công cụ CI, scanner, code generator hoặc plugin.

Các JDK này có thể khác feature release hoặc vendor. Vì vậy, khi kiểm tra môi trường cần ghi nhận từng vị trí thay vì chỉ chạy `java -version` ở terminal của lập trình viên.

### 10.1. Kiểm tra runtime đang nằm trên PATH

```bash
java -version
javac -version
```

Hai lệnh này giúp nhận diện runtime và compiler đang được gọi từ `PATH`. Chúng chưa chứng minh Gradle hoặc ứng dụng production cũng đang dùng đúng JDK đó.

Để xem thêm thông tin hệ thống:

```bash
java -XshowSettings:properties -version
```

Các thuộc tính hữu ích gồm `java.vendor`, `java.runtime.version`, `java.vm.name`, `os.name` và `os.arch`. Khi thu thập bằng chứng migration, lưu nguyên output để có thể so sánh trước và sau.

### 10.2. Kiểm tra JVM chạy Gradle

```bash
./gradlew -version
```

Output cho biết JVM mà Gradle đang sử dụng. JVM này có thể khác JDK toolchain mà task biên dịch sử dụng.

### 10.3. Khai báo toolchain và vendor trong Gradle

Ví dụ Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
```

Khai báo này yêu cầu toolchain Java 21 từ vendor được chỉ định. Khả năng tự động tìm hoặc tải JDK còn phụ thuộc vào cấu hình toolchain resolver và môi trường build. Cú pháp và các vendor spec khả dụng cần đối chiếu với phiên bản Gradle của dự án.

Nếu chỉ cần biên dịch bằng JDK 21 nhưng phát hành bytecode tương thích Java 17, có thể cấu hình `--release` thông qua Gradle:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Trong trường hợp này, compiler có thể chạy trên JDK 21, nhưng mã nguồn được biên dịch theo mức ngôn ngữ, bytecode và API Java 17 mà `--release` quy định. Điều đó không tự động bảo đảm mọi dependency, plugin hoặc runtime của ứng dụng đều tương thích Java 17; các thành phần này vẫn phải được kiểm tra riêng.

### 10.4. Kiểm tra container và production

Đối với container, kiểm tra image tag, digest, OS base, architecture và phiên bản JDK bên trong image. Tag như `21` hoặc `21-jre` có thể được cập nhật theo thời gian; nếu cần tái lập build, cần quản lý digest và chính sách cập nhật image phù hợp.

Với máy chủ production, kiểm tra tiến trình thực tế đang chạy binary nào, `JAVA_HOME` của service, cấu hình systemd/service manager, biến môi trường container và cơ chế rollout. Giá trị `JAVA_HOME` trong shell đăng nhập không nhất thiết là JDK mà service đã được khởi chạy.

## 11. Lập ma trận hỗ trợ JDK cho migration

Trước khi nâng cấp, tạo ma trận cho từng môi trường và consumer. Ví dụ:

| Thành phần | Feature version | Distribution/vendor | Update level | Mục đích |
|---|---|---|---|---|
| Developer workstation | 21 | Distribution được nhóm chuẩn hóa | Theo baseline của nhóm | Viết code và chạy test local |
| CI build agent | 21 | Cùng vendor hoặc vendor đã được kiểm chứng | Bản cập nhật được phê duyệt | Chạy Gradle/Maven và pipeline |
| Compile toolchain | 21 | Theo toolchain policy | Bản cập nhật được phê duyệt | Biên dịch source và test |
| Runtime container | 21 | Runtime image đã xác minh | Theo lịch cập nhật image | Chạy ứng dụng |
| Production host | 21 | Vendor được vận hành hỗ trợ | Theo lịch vá production | Vận hành chính thức |

Ma trận này chỉ là ví dụ. Nếu hệ thống có consumer vẫn cần Java 17 hoặc nhiều kiến trúc CPU, hãy thêm các dòng tương ứng. Mỗi dòng nên có owner, ngày xác minh, nguồn tải, chính sách cập nhật và mốc kết thúc hỗ trợ.

Một ma trận tốt cần trả lời được:

1. Thành phần nào đang dùng JDK nào và ai chịu trách nhiệm cập nhật?
2. Feature version và update level có đồng nhất theo yêu cầu của tổ chức không?
3. Distribution có hỗ trợ đúng OS, architecture và container không?
4. Mốc kết thúc hỗ trợ nào sẽ đến trước trong toàn bộ chuỗi build và runtime?
5. Có consumer nào bị khóa ở một JDK cũ do framework, plugin hoặc dependency không?
6. Có quy trình phát hiện và xử lý bản vá bảo mật khẩn cấp không?

## 12. Lộ trình chuyển đổi và duy trì bản cập nhật

### Bước 1: Kiểm kê hiện trạng

Thu thập output phiên bản từ local, CI, build agent, container và production. Ghi lại feature release, update level, vendor, OS, architecture, cách cài đặt và owner.

### Bước 2: Xác định mục tiêu kỹ thuật

Chọn feature release mục tiêu dựa trên yêu cầu ngôn ngữ/API, framework, dependency, Gradle/Maven và thời hạn hỗ trợ. Xác định có cần đổi vendor hoặc distribution cùng lúc hay không. Nếu đổi cả feature release và vendor trong một lần, việc phân tích nguyên nhân lỗi sẽ khó hơn; có thể tách thành các giai đoạn khi điều kiện dự án cho phép.

### Bước 3: Đối chiếu chính sách hỗ trợ

Đọc lifecycle và điều khoản của đúng distribution. Xác định mốc cập nhật bảo mật công khai, hỗ trợ thương mại, extended support và end-of-life. Lưu nguồn tham chiếu cùng ngày kiểm tra vì chính sách của vendor có thể được cập nhật.

### Bước 4: Chuẩn hóa build và runtime

Khai báo toolchain, compiler release, Gradle JVM, container base image và runtime mục tiêu. Đảm bảo pipeline không vô tình dùng JDK khác do `PATH`, `JAVA_HOME` hoặc image tag trôi nổi.

### Bước 5: Kiểm thử theo môi trường thật

Build, unit test, integration test, smoke test và kiểm tra hiệu năng trên distribution mục tiêu. Với thay đổi vendor, kiểm tra thêm certificate, crypto provider, timezone, locale, native library và công cụ chẩn đoán.

### Bước 6: Phát hành và theo dõi

Triển khai thử trên môi trường staging, sau đó rollout có kiểm soát. Theo dõi lỗi JVM, GC, memory, startup, TLS, logging và các chỉ số nghiệp vụ. Ghi nhận phiên bản đầy đủ để có thể truy vết sự cố.

### Bước 7: Duy trì chu kỳ cập nhật

Thiết lập lịch rà soát security advisory, cập nhật JDK, container image và OS. Xác định người phê duyệt, cách kiểm thử, thời gian triển khai bản vá và phương án rollback. Không nên chờ tới cuối vòng đời mới bắt đầu lên kế hoạch nâng cấp.

## 13. Các hiểu lầm thường gặp

**“Cùng Java 21 thì mọi JDK giống hệt nhau.”** Các distribution hướng tới cùng Java SE release phải đáp ứng nền tảng tương ứng, nhưng vẫn có khác biệt về build, patch, đóng gói, OS support, công cụ và chính sách hỗ trợ.

**“OpenJDK là một vendor duy nhất.”** OpenJDK là dự án/cơ sở mã nguồn; nhiều tổ chức có thể xây dựng và phát hành distribution từ mã nguồn đó.

**“Java 21 LTS có nghĩa mọi vendor hỗ trợ đến cùng một ngày.”** LTS không thay thế lifecycle của từng sản phẩm. Cần tra cứu đúng vendor, distribution, loại hỗ trợ và điều khoản.

**“Cài JDK mới nhất là đủ.”** Cần xác định JDK mới nhất có nằm trong phạm vi tương thích của framework, plugin, dependency, OS và môi trường production không; đồng thời phải kiểm tra update policy và cách rollout.

**“Build thành công trên máy lập trình viên chứng minh production đã đúng JDK.”** Build daemon, toolchain, container và service production có thể dùng các JDK khác nhau. Cần kiểm tra từng môi trường.

**“Mã nguồn mở đồng nghĩa mọi cách sử dụng đều miễn phí và có hỗ trợ.”** License của mã nguồn, điều khoản của binary distribution và hợp đồng hỗ trợ là các vấn đề riêng. Phải đọc điều khoản áp dụng cho tổ chức và môi trường sử dụng.

## 14. Checklist xác nhận phiên bản và chính sách hỗ trợ

- [ ] Đã ghi rõ Java SE feature release mục tiêu.
- [ ] Đã ghi nhận JDK distribution, vendor và update/build level thực tế.
- [ ] Đã phân biệt JDK chạy Gradle, toolchain biên dịch và runtime production.
- [ ] Đã kiểm tra OS, CPU architecture, container image và native dependency.
- [ ] Đã xác minh tuyên bố tương thích Java SE của distribution khi yêu cầu dự án cần điều đó.
- [ ] Đã đọc lifecycle, lịch security update, end-of-life và điều khoản sử dụng của đúng vendor.
- [ ] Đã xác định yêu cầu SLA, hỗ trợ thương mại, tuân thủ và chứng nhận nếu có.
- [ ] Đã kiểm thử trên distribution và môi trường gần với production.
- [ ] Đã có lịch cập nhật, owner, quy trình xử lý CVE và phương án rollback.
- [ ] Đã lưu nguồn tham chiếu và ngày xác minh chính sách hỗ trợ.

## Kết luận

Java SE release mô tả phiên bản nền tảng; JDK là bộ công cụ và runtime hiện thực nền tảng đó; JDK distribution là sản phẩm cụ thể do nhà cung cấp xây dựng, đóng gói và hỗ trợ. LTS, lịch cập nhật bảo mật, điều khoản sử dụng và thời hạn hỗ trợ phụ thuộc vào từng nhà cung cấp và dòng sản phẩm. Trong migration, cần ghi nhận đầy đủ feature version, vendor, update level, môi trường build/runtime và lifecycle hỗ trợ. Cách làm này giúp nhóm chọn đúng JDK cho hệ thống, tránh nhầm lẫn giữa tương thích kỹ thuật và cam kết vận hành, đồng thời chủ động duy trì các bản vá trong suốt vòng đời ứng dụng.
