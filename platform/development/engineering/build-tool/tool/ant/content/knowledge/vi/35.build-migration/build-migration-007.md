# Tiêu chí giữ Ant, kết hợp công cụ hoặc kết thúc chuyển đổi build

## 1. Bài toán lựa chọn sau khi xem xét chuyển đổi

Trong một dự án Java đang sử dụng **Apache Ant**, việc cân nhắc chuyển sang Maven, Gradle hoặc một hệ thống build khác không nhất thiết phải kết thúc bằng hành động thay thế toàn bộ `build.xml`. Ant có thể tiếp tục phục vụ tốt một số mô-đun, có thể cùng tồn tại với một công cụ mới, hoặc có thể được loại bỏ sau khi chức năng build đã chuyển hoàn toàn.

Vấn đề cốt lõi là chọn **trạng thái vận hành phù hợp với nhu cầu dự án và có thể chứng minh bằng bằng chứng**:

1. **Giữ Ant:** Ant tiếp tục là công cụ chính cho phần build được xem xét, với các giới hạn và trách nhiệm bảo trì rõ ràng.
2. **Kết hợp công cụ:** Ant và công cụ khác cùng tồn tại trong một khoảng thời gian hoặc lâu dài, mỗi công cụ có phạm vi và đầu ra xác định.
3. **Kết thúc chuyển đổi:** Phạm vi được chuyển đã đạt tiêu chí nghiệm thu; quy trình chính sử dụng công cụ đích và các đường thực thi Ant thuộc phạm vi đó được ngừng sử dụng theo kế hoạch.

Đây là ba kết quả **đều có thể hợp lệ**. “Chuyển đổi thành công” không đồng nghĩa với “xóa mọi tệp XML của Ant”. Nếu một dự án giữ Ant vì chi phí thay thế cao, rủi ro cao nhưng yêu cầu hiện tại vẫn được đáp ứng tốt, đó có thể là quyết định kỹ thuật có căn cứ. Ngược lại, nếu cần dependency resolution, test/report chuẩn hóa, plugin và tích hợp IDE hiện đại mà cấu hình Ant hiện tại gây nhiều chi phí, tiếp tục giữ Ant vô thời hạn cũng có thể không còn hợp lý.

Bài học tập trung vào cách xác lập tiêu chí, phương pháp thu thập chứng cứ, thiết kế vùng trách nhiệm của từng công cụ và cổng nghiệm thu để kết thúc quá trình chuyển đổi một cách có kiểm soát.

## 2. Hiểu đúng vai trò của Ant trong hệ thống hiện tại

Ant là công cụ thực thi các **target** và **task** khai báo trong `build.xml`. Một dự án có thể dùng Ant để biên dịch Java, chạy kiểm thử, sao chép tài nguyên, tạo JAR/WAR, sinh mã, dựng gói cài đặt hoặc gọi công cụ bên ngoài. Các bước này thường liên kết qua `depends`, property và file bổ trợ.

Ví dụ:

```xml
<project name="legacy-app" default="package" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>

    <target name="clean">
        <delete dir="build"/>
        <delete dir="dist"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/legacy-app.jar"
             basedir="${classes.dir}"/>
    </target>
</project>
```

Đoạn ví dụ này mô tả **quy trình**, nhưng không tự chứng minh rằng dự án đã quản lý dependency đầy đủ, có bộ test, tạo artifact có thể tái lập, hoặc có đủ điều kiện phát hành. Trước khi quyết định chuyển đổi, phải tìm hiểu những yếu tố thật sự đang được Ant điều khiển:

| Phạm vi | Câu hỏi cần trả lời |
| --- | --- |
| Source và resource | Ant biên dịch những source set nào? Có file sinh mã hay resource riêng theo môi trường không? |
| Dependency | JAR lấy từ `lib/`, Apache Ivy, repository nội bộ hay đường dẫn máy cá nhân? Phiên bản có cố định không? |
| Kiểm thử | Test nào chạy bằng Ant? Có integration test, test cần database, test có điều kiện skip không? |
| Artifact | Tạo JAR, WAR, ZIP, installer hay nhiều loại? Có manifest, chữ ký, tài liệu, checksum không? |
| Công cụ bổ trợ | Có `<exec>` gọi shell, code generator, task bên thứ ba, custom Ant task hay script riêng không? |
| CI/CD | Pipeline gọi target nào? Có job phát hành sử dụng output nào? |
| Môi trường | JDK/Ant cần phiên bản gì? Có phụ thuộc Windows, Linux, encoding hoặc filesystem không? |
| Người dùng | Developer, CI, release engineer và automation đang gọi lệnh nào? |

Không nên chỉ nhìn số dòng `build.xml` để kết luận độ phức tạp. Một dự án có file Ant ngắn nhưng gọi tới nhiều script ẩn vẫn có thể khó chuyển đổi hơn một file dài nhưng dùng những task chuẩn.

## 3. Định nghĩa mục tiêu trước khi chọn công cụ

Một quyết định tốt bắt đầu bằng **vấn đề cần giải quyết**, không bắt đầu bằng sở thích công cụ.

Ví dụ, dự án có thể có các mục tiêu:

- **Giảm thời gian bảo trì:** thay các đoạn tự viết để tải dependency, gom báo cáo hoặc kết hợp test bằng cơ chế chuẩn.
- **Tăng khả năng tái lập:** build từ clean checkout với phiên bản JDK và dependency được cố định.
- **Cải thiện CI:** dùng chung lệnh với local, trả đúng mã lỗi, có test report và artifact rõ ràng.
- **Hỗ trợ nhiều mô-đun:** dependency giữa mô-đun và vòng đời build hiện tại quá phức tạp.
- **Giảm rủi ro khi nâng JDK:** toolchain, compiler options và plugin được quản lý nhất quán.
- **Duy trì sản phẩm legacy ổn định:** tránh thay đổi một hệ thống ít sửa nhưng rất nhạy cảm với đầu ra.
- **Đơn giản hóa onboarding:** developer mới chạy được build bằng tài liệu và công cụ có thể cài đặt lặp lại.

Mỗi mục tiêu cần có chỉ dấu kiểm chứng. Ví dụ:

| Mục tiêu | Dữ liệu cần thu thập | Tiêu chí nghiệm thu minh họa |
| --- | --- | --- |
| Clean build tự động | Thời gian từ checkout mới đến `verify` | Chạy thành công trên runner chuẩn mà không cần file thủ công |
| Giảm lỗi dependency | Lỗi thiếu JAR hoặc sai version theo một giai đoạn đo | Không còn dependency ẩn vào thư mục người dùng |
| Giữ hành vi sản phẩm | Test, manifest, classpath, artifact và smoke test | Các hành vi bắt buộc được xác nhận tương đương |
| Chuẩn hóa CI | Lệnh, JDK, report, exit code | Local và CI có một điểm vào xác nhận được tài liệu hóa |
| Dễ bảo trì | Số custom script bắt buộc, số bước thao tác thủ công | Mỗi bước có owner, cách chạy và cơ chế lỗi rõ |
| Giảm thời gian build | Dữ liệu đo nhiều lần trên môi trường so sánh được | Đạt ngưỡng thời gian do nhóm thống nhất |

Các ngưỡng như “giảm 20% thời gian” hoặc “hoàn thành trong 10 phút” chỉ nên là **ví dụ**, không phải chuẩn bắt buộc. Nếu chưa có số liệu nền, hãy đo trước khi đưa ra mục tiêu.

## 4. Khi nào nên giữ Apache Ant?

Giữ Ant là lựa chọn có cơ sở khi **lợi ích thay thế chưa đủ lớn so với chi phí và rủi ro**, đồng thời dự án vẫn đáp ứng yêu cầu vận hành.

### 4.1. Dấu hiệu ủng hộ việc giữ Ant

**Build đã ổn định và dễ tái hiện.** Từ một clean checkout, nhóm có thể chạy target chuẩn để tạo đúng artifact, test chạy đầy đủ, dependency được cung cấp theo một cơ chế rõ ràng và CI báo lỗi đúng khi thất bại.

**Dự án có các tác vụ đặc thù.** Ant có thể đang tích hợp với một compiler ngoài, hệ thống sinh mã cũ, đóng gói cho thiết bị hoặc quy trình phát hành đặc biệt. Việc chuyển các bước đó sang công cụ khác sẽ tạo nhiều mã nối mới mà chưa mang lại lợi ích đáng kể.

**Tần suất thay đổi thấp.** Một ứng dụng bảo trì với ít dependency và ít thay đổi có thể không cần một vòng đời build phức tạp. Tuy nhiên, ít thay đổi **không** có nghĩa được bỏ qua cập nhật bảo mật, JDK hay kiểm thử.

**Đội ngũ nắm rõ cơ chế vận hành.** Có người chịu trách nhiệm `build.xml`, có tài liệu cho target chính và có kế hoạch phục hồi khi custom task hoặc môi trường chạy hỏng.

**Không có yêu cầu mới mà Ant không đáp ứng.** Nếu nguyên nhân chuyển đổi chỉ là “tool mới phổ biến hơn” nhưng nhu cầu chức năng không đổi, quyết định giữ Ant có thể tránh một dự án di chuyển tốn kém.

### 4.2. Những điều kiện tối thiểu khi quyết định giữ Ant

Giữ công cụ không đồng nghĩa giữ nguyên mọi vấn đề. Một trạng thái “Ant được duy trì có chủ đích” nên có:

1. **Lệnh chính được chuẩn hóa**, ví dụ `ant clean verify`, kèm mô tả target nào chạy kiểm thử và target nào tạo artifact.
2. **JDK và Ant được quản lý phiên bản** hoặc có ma trận phiên bản hỗ trợ.
3. **Dependency không dựa vào file ngầm trên máy người bảo trì**; nguồn lấy thư viện và phiên bản phải rõ ràng.
4. **Build trả mã lỗi đúng**; tác vụ `<exec>`, `<java>` hoặc kiểm thử không được âm thầm bỏ qua thất bại.
5. **CI xác nhận clean build và lưu report/artifact** theo nhu cầu dự án.
6. **Các script/custom task quan trọng có owner** và cách xử lý khi phụ thuộc không còn tương thích.
7. **Rủi ro còn lại được ghi nhận**, đặc biệt là rủi ro toolchain cũ, thiếu nhân sự bảo trì hoặc không còn môi trường build được hỗ trợ.

Nếu Ant build chỉ chạy được trên laptop của một người, thiếu JAR trong repository và không có tài liệu môi trường, “nó vẫn đang chạy” chưa phải bằng chứng đủ mạnh để quyết định giữ lâu dài.

### 4.3. Bài toán nên sửa Ant trước khi quyết định chuyển

Một số vấn đề có thể xử lý trực tiếp:

- Biên dịch source bằng `<javac>` với `release`/`encoding` rõ ràng.
- Chuẩn hóa property và path ID thay vì hard-code đường dẫn.
- Tách target `clean`, `compile`, `test`, `package`, `verify`.
- Dùng Ivy hoặc quy trình dependency đã được kiểm soát thay cho các JAR tải thủ công.
- Đưa bước test vào target chính của CI.
- Loại bỏ các `<exec>` bỏ qua mã lỗi.
- Ghi log môi trường và artifact không nhạy cảm để dễ chẩn đoán.

Nếu các cải thiện này giải quyết được mục tiêu với ít thay đổi, có thể giữ Ant. Nếu mỗi cải thiện đòi hỏi thêm custom logic lớn và phải bảo trì một hệ thống build riêng, đó là tín hiệu cân nhắc công cụ khác.

## 5. Khi nào nên kết hợp Ant với công cụ khác?

**Kết hợp công cụ** phù hợp khi một phần build hiện tại cần giữ nguyên, nhưng các phần mới hưởng lợi rõ rệt từ Maven, Gradle hoặc công cụ chuyên biệt.

Một số tình huống:

| Tình huống | Phương án kết hợp |
| --- | --- |
| Module legacy dùng custom Ant task quan trọng | Giữ Ant cho module đó; module Java mới dùng Maven/Gradle |
| Build hiện tại tạo mã nguồn từ công cụ cũ | Ant làm bước sinh mã có đầu ra xác định; công cụ mới biên dịch/kiểm thử |
| Dự án cần dependency graph và test lifecycle chuẩn | Maven/Gradle quản lý các module mới; Ant chỉ giữ khâu đóng gói đặc thù |
| CI cần chuyển dần mà không dừng phát hành | CI chạy build cũ và mới song song để so sánh trong thời gian chuyển tiếp |
| Một phần output phải giữ định dạng legacy | Ant sản xuất artifact legacy; bước mới xử lý các artifact còn lại |
| Hệ thống có nhiều repository/mô-đun tương đối độc lập | Mỗi phần dùng tool phù hợp; pipeline phối hợp qua artifact hoặc job dependency |

Kết hợp lâu dài có thể đúng, nhưng chỉ khi **ranh giới rõ ràng**. Nếu cả Ant và Gradle cùng biên dịch cùng tập source rồi viết chung một thư mục `build/classes`, việc ai sở hữu output và artifact sẽ trở nên khó xác định.

### 5.1. Xác lập một công cụ sở hữu mỗi đầu ra

Mẫu ranh giới nên có:

```text
CI pipeline
   |
   +-- Ant: generate-legacy-sources
   |      └── build/generated/legacy/
   |
   +-- Gradle/Maven: compile + test
   |      └── build/libs/app.jar hoặc target/app.jar
   |
   +-- Công cụ đóng gói riêng (nếu cần)
          └── dist/release.zip
```

Bảng sở hữu:

| Đầu ra | Owner được chỉ định | Consumer | Ghi chú |
| --- | --- | --- | --- |
| `generated/legacy/*.java` | Ant | Gradle/Maven | Chỉ một bước được ghi đè |
| `build/classes` hoặc `target/classes` | Công cụ biên dịch mới | Bước test, package | Không để Ant sửa cùng lúc |
| `build/reports/tests` hoặc `target/surefire-reports` | Công cụ chạy test | CI | CI đọc report từ đúng thư mục |
| `dist/release.zip` | Bước đóng gói đã chọn | Deployment | Nguồn artifact rõ, version rõ |

Việc đặt một “owner” cho output giúp tránh race condition, file cũ và bug khó tái hiện.

### 5.2. Chọn hướng điều phối

Có ba mô hình thường gặp:

**CI điều phối hai công cụ:**

```text
CI:
  1. ant generate-legacy
  2. ./gradlew test assemble
  3. publish artifact của Gradle
```

Ưu điểm: từng lệnh rõ ràng, log tách biệt và trạng thái lỗi dễ quan sát. Nhược điểm: một developer có thể phải chạy hai lệnh, trừ khi có script hoặc target tổng hợp được duy trì.

**Ant gọi công cụ mới:**

```xml
<project name="bridge" default="verify">
    <target name="legacy-generate">
        <!-- Gọi custom task cũ để tạo đầu ra cần thiết -->
    </target>

    <target name="modern-verify" depends="legacy-generate">
        <exec executable="gradle"
              dir="modern-module"
              failonerror="true">
            <arg value="verify"/>
        </exec>
    </target>

    <target name="verify" depends="modern-verify"/>
</project>
```

Đây là **ví dụ mô hình**: giả định `modern-module` có một task `verify` được định nghĩa và lệnh `gradle` đã được cài, có trong `PATH`. Trong thực tế, nên ưu tiên Gradle Wrapper của dự án nếu dùng Gradle, và xử lý tên launcher tương ứng Windows/Linux. Ant `<exec>` cần được cấu hình để truyền tham số, thư mục làm việc và trạng thái thất bại đúng. Với `failonerror="true"`, tiến trình trả mã thoát khác 0 sẽ khiến target thất bại, giúp CI không báo thành công giả.

**Công cụ mới gọi Ant:**

```text
Gradle/Maven lifecycle
   |
   +-- Bước tích hợp được cấu hình rõ ràng
         |
         +-- ant -f legacy/build.xml generate-legacy
```

Cách này phù hợp khi công cụ mới đã sở hữu phần lớn quy trình và Ant chỉ còn một tác vụ đặc thù. Cần cấu hình thời điểm chạy, đầu vào/đầu ra, working directory, error propagation và dependency đúng. Tránh để Ant gọi Gradle trong khi Gradle lại gọi chính Ant target đó, gây vòng lặp.

**Quy tắc chọn:** nên có **một điểm vào chính** cho developer/CI đối với từng sản phẩm cần build, dù bên dưới có thể gọi nhiều công cụ. Điểm vào chính phải được tài liệu hóa.

### 5.3. Dùng artifact làm hợp đồng giữa hai công cụ

Nếu Ant tạo mã nguồn hoặc JAR rồi Gradle/Maven sử dụng, hợp đồng giao tiếp nên bao gồm:

- Đường dẫn và cấu trúc artifact.
- Phiên bản định dạng, encoding và phiên bản Java nếu là bytecode.
- Quy tắc tạo mới/xóa output cũ.
- Khi nào coi output đã hoàn tất, cần điều kiện `fail` nào khi thiếu.
- Cơ chế truyền revision/phiên bản nếu artifact cần truy vết.
- Ai được phép ghi tệp, ai chỉ đọc tệp.
- CI có lưu được log/report từ cả hai phía hay không.

Ví dụ, một bước kiểm tra sự tồn tại của artifact do công cụ trước tạo:

```xml
<target name="verify-generated-source">
    <available file="build/generated/legacy/com/example/Generated.java"
               type="file"
               property="legacy.generated.exists"/>

    <fail unless="legacy.generated.exists"
          message="[verify-generated-source] Thiếu Generated.java từ bước Ant generate-legacy"/>
</target>
```

Kiểm tra tệp tồn tại là một **điều kiện sơ bộ**; với artifact quan trọng, còn có thể cần kiểm tra schema, nội dung, hash hoặc chạy compiler/test thực sự. Đừng coi riêng `available` là bằng chứng tích hợp hoàn chỉnh.

## 6. Khi nào nên chuyển hoàn toàn khỏi Ant?

Nên nghiêng về chuyển hoàn toàn khi nhiều điều kiện cùng xuất hiện:

- Phần lớn source, test, dependency và artifact đã được mô hình hóa tốt trong công cụ mới.
- Ant chỉ còn làm wrapper gọi nhiều script hoặc gọi chính công cụ mới mà không tạo giá trị bổ sung.
- Việc duy trì hai công cụ tăng chi phí CI, onboarding và xử lý lỗi.
- Custom task cũ có thể thay bằng plugin/task chuẩn hoặc một bước có interface rõ.
- Các target Ant còn lại không được external caller sử dụng, hoặc đã có kế hoạch thay thế caller.
- Có đủ test và bằng chứng chứng minh sản phẩm mới tương đương ở những hành vi cần giữ.
- Toolchain mới có owner, tài liệu, kiểm soát dependency và phương án rollback trong giai đoạn triển khai.

Ví dụ:

```text
Trước:
  CI → ant clean verify package release

Chuyển tiếp:
  CI → ant legacy-generate
     → gradle clean test assemble
     → so sánh artifact/báo cáo

Sau:
  CI → gradle clean test assemble
     → publish artifact mới

Phần Ant:
  Đã loại bỏ khỏi critical path,
  không còn consumer và không còn tác vụ cần duy trì.
```

Tuy nhiên, không phải dự án nào cũng cần đạt trạng thái cuối này. **Kết thúc dự án chuyển đổi** có thể là quyết định chính thức giữ một phần Ant nếu những target đó đã có owner, giới hạn rõ và được vận hành bền vững. Cần phân biệt *dừng một dự án chuyển đổi vì mục tiêu đã đạt* với *retire Ant hoàn toàn*.

## 7. Ma trận quyết định giữ, kết hợp hay thay thế

Bảng sau giúp đánh giá từng tiêu chí. Các mức “thấp/vừa/cao” cần được gắn với bằng chứng của dự án, không chỉ là cảm nhận.

| Tiêu chí | Nghiêng về giữ Ant | Nghiêng về kết hợp | Nghiêng về chuyển hoàn toàn |
| --- | --- | --- | --- |
| Độ ổn định build Ant | Cao, clean build tái hiện tốt | Ổn định ở phần legacy, phần mới cần tool khác | Lỗi lặp nhiều và khó khắc phục bằng cải tiến Ant |
| Mức độ phụ thuộc custom task | Nhiều task quan trọng, chưa có thay thế | Chỉ giữ task đặc thù | Đã thay thế hoặc không còn cần |
| Dependency graph | Đơn giản, được quản lý rõ | Một phần cần quản lý nâng cao | Phần lớn dự án hưởng lợi từ lifecycle/dependency của tool mới |
| Số module và build variants | Ít, dễ theo dõi | Legacy và module mới tách rõ | Có nhu cầu đồng bộ nhiều module phức tạp |
| Chi phí vận hành hai công cụ | Không phát sinh | Chấp nhận được với ranh giới rõ | Chi phí lớn hơn lợi ích của Ant |
| Rủi ro thay đổi artifact | Cao, khó xác minh tương đương | Cần shadow run/giai đoạn chuyển tiếp | Đã có test và gate đủ tin cậy |
| Yêu cầu nâng cấp JDK/toolchain | Ant đáp ứng tốt | Ant cũ ở một nhánh, nhánh mới cần upgrade | Ant/custom task cản trở nâng cấp |
| Năng lực nhóm | Có owner hiểu Ant | Có owner cho cả hai phía | Nhóm đã vận hành thành thạo tool mới |
| Thời gian và nguồn lực chuyển đổi | Hạn chế, chưa có nhu cầu cấp thiết | Có thể chuyển theo mô-đun | Có đủ nguồn lực và lộ trình nghiệm thu |

### 7.1. Mẫu chấm điểm thực tế

Có thể đánh giá theo **trọng số**, chẳng hạn:

| Tiêu chí | Trọng số ví dụ | Giữ Ant (1–5) | Kết hợp (1–5) | Chuyển (1–5) |
| --- | ---: | ---: | ---: | ---: |
| Đáp ứng yêu cầu chức năng | 30% | 4 | 5 | 5 |
| Rủi ro triển khai | 25% | 5 | 4 | 2 |
| Chi phí bảo trì trong hai năm | 20% | 2 | 3 | 5 |
| Tính tái lập và CI | 15% | 3 | 4 | 5 |
| Năng lực và onboarding | 10% | 4 | 3 | 4 |

Điểm trong bảng chỉ là **minh họa giả định**, không áp dụng mặc định cho bất kỳ dự án nào. Nếu tính tổng trọng số, dùng công thức:

\[
S_{\text{phương án}}=\sum_i w_i \times s_i,\qquad \sum_i w_i=1.
\]

Trong đó `w_i` là mức quan trọng do nhóm đồng thuận và `s_i` là điểm được hỗ trợ bằng chứng. Tổng điểm giúp nhìn rõ đánh đổi, nhưng **không thay thế các điều kiện bắt buộc**: một phương án điểm cao vẫn không được chọn nếu vi phạm tiêu chí pháp lý, bảo mật, artifact hoặc vận hành.

### 7.2. Đặt “điều kiện loại trừ” trước khi cộng điểm

Ví dụ những điều kiện có thể buộc nhóm không chọn một phương án:

- Không thể tạo artifact mà hệ thống triển khai hiện tại chấp nhận.
- Không chạy được test bắt buộc, nhưng pipeline vẫn báo thành công.
- Một phần build dựa vào credential cá nhân hoặc custom task không còn được hỗ trợ.
- Không có phương án khôi phục khi thay đổi cơ chế phát hành có ảnh hưởng lớn.
- Không thể xác nhận những bước tạo mã, ký gói hoặc kiểm tra an toàn đang được bảo toàn.

Các điều kiện này cần được định nghĩa theo thực tế dự án. Không đặt điểm “bảo trì tốt” để bù cho việc mất một chức năng bắt buộc.

## 8. Kiểm chứng tính tương đương giữa Ant và công cụ mới

Một chuyển đổi build chỉ thực sự có giá trị khi **đầu ra và hành vi được yêu cầu** được bảo toàn. Việc cả hai lệnh đều trả exit code 0 là điều kiện cần, không phải toàn bộ bằng chứng.

### 8.1. Lập bản đồ trước khi triển khai

Bảng ánh xạ ví dụ:

| Trách nhiệm | Ant hiện tại | Công cụ đích | Kết quả cần so |
| --- | --- | --- | --- |
| Xóa output | `clean` | `clean` | Không còn artifact cũ gây nhiễu |
| Sinh nguồn | `generate-sources` | Task/plugin đã chọn | Source sinh, encoding, tên class |
| Biên dịch source chính | `compile` | `compileJava` hoặc `compile` | Target release, classes, resources |
| Biên dịch test | `compile-tests` | `compileTestJava` / `test-compile` | Test classpath và số test phát hiện |
| Chạy test | `test` | `test` | Test pass/fail/skip và report |
| Đóng gói | `package` | `jar`/`assemble`/`package` | Artifact và metadata quan trọng |
| Sinh tài liệu | `docs` | Task/plugin tương ứng | File/format/link bắt buộc |
| Phát hành | `publish` | Task/job tương ứng | Đích, quyền truy cập, version, idempotency |

Tên task trong bảng chỉ là **ví dụ**, khác nhau theo công cụ và plugin. Cần đọc build script thực tế để xác định tương đương, không suy ra chỉ từ tên.

### 8.2. So theo nhiều cấp độ

**Cấp độ 1 — Giao diện build:** có lệnh chuẩn để clean, verify, package, chạy local và CI; lỗi trả mã thoát khác 0 khi phải thất bại.

**Cấp độ 2 — Tập công việc:** cùng source set, tài nguyên, file sinh mã, bộ test và các điều kiện skip bắt buộc.

**Cấp độ 3 — Artifact:** tên file, cấu trúc JAR/WAR/ZIP, các entry quan trọng, manifest, cấu hình runtime, compatibility của classfile.

**Cấp độ 4 — Hành vi:** smoke test và integration test trên runtime mục tiêu; sản phẩm mới hoạt động như bản trước tại các điểm tích hợp.

**Cấp độ 5 — Tái lập và vận hành:** clean checkout, CI runner chuẩn, dependency cố định, báo cáo lỗi rõ, phát hành và rollback được nếu nằm trong phạm vi.

Cần phân biệt **tương đương chức năng** với **giống hệt từng byte**. Hai JAR có thể khác timestamp, thứ tự entry hoặc metadata nhưng chứa chương trình thực thi tương đương. Nếu dự án yêu cầu reproducible artifact, mã băm phải giống nhau dưới điều kiện build được kiểm soát; nếu không yêu cầu, nên so manifest, class, resource và hành vi.

### 8.3. Ví dụ thu thập bằng chứng artifact

Với hai artifact đã tạo ở hai thư mục riêng:

```bash
jar tf artifacts/ant/app.jar
jar tf artifacts/new/app.jar

javap -verbose -classpath artifacts/ant/app.jar com.example.App
javap -verbose -classpath artifacts/new/app.jar com.example.App
```

Trên Linux/macOS có thể tính:

```bash
sha256sum artifacts/ant/app.jar
sha256sum artifacts/new/app.jar
```

Trên Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath artifacts/ant/app.jar
Get-FileHash -Algorithm SHA256 -LiteralPath artifacts/new/app.jar
```

Nếu hash khác, điều tra file/metadata khác trước khi kết luận logic thay đổi. Nếu hash giống, đó là bằng chứng hai tệp có nội dung byte giống hệt tại thời điểm so sánh, nhưng **chưa tự chứng minh** mọi yêu cầu triển khai đã được thử.

### 8.4. Xác định mức “đủ tương đương”

Mỗi loại dự án có hợp đồng khác nhau. Ví dụ:

- **Library:** tọa độ artifact, public API, bytecode compatibility, transitive dependency và kết quả test.
- **Ứng dụng web:** WAR/JAR, resource, classpath, port/config, startup, health check, test tích hợp.
- **Ứng dụng desktop:** installer, resource, chữ ký, runtime đóng gói, đường dẫn sau cài đặt.
- **Công cụ CLI:** tên binary, tham số, exit code, stdout/stderr và khả năng chạy trên OS mục tiêu.
- **Code generator:** vị trí file sinh, schema, encoding, tính ổn định khi chạy lại và tác động lên source.

“Đủ tương đương” phải được thống nhất **trước khi xóa đường build cũ**, tránh chuyện hạ tiêu chí khi phát hiện thiếu chức năng.

## 9. Chiến lược chuyển đổi từng phần

Chuyển đổi từng phần thường giúp phát hiện khác biệt sớm, không làm mất đường build hoạt động trước khi có bằng chứng.

### Giai đoạn A — Kiểm kê và tạo đường cơ sở

Thu thập:

- Danh sách target được gọi từ local, CI, release và automation.
- Input/output của mỗi target, custom task, script, property và dependency.
- Phiên bản Ant, JDK, thư viện và OS hỗ trợ.
- Lệnh clean build chuẩn.
- Test report, artifact mẫu, thời gian build và lỗi phổ biến.
- Những tác vụ có side effect: upload, ký gói, deploy, xóa/tạo dữ liệu ngoài workspace.

Bản đồ đầu vào/đầu ra là cơ sở để chọn ranh giới chuyển đổi, không nên bắt đầu bằng sao chép `build.xml` sang một DSL mới.

### Giai đoạn B — Chọn một phạm vi ít phụ thuộc

Chẳng hạn chuyển riêng module thư viện có dependency đơn giản hoặc bước compile/test không có tác vụ phát hành. Tránh bắt đầu bằng target release vừa build, vừa ký, vừa deploy nếu chưa hiểu hết luồng.

### Giai đoạn C — Dựng luồng mới bên cạnh luồng cũ

Trong giai đoạn này:

```text
Source revision X
    |
    +-- Ant clean + verify + package
    |        └── artifacts/ant/
    |
    +-- Tool mới clean + verify + package
             └── artifacts/new/

So sánh test, artifact, log, thời gian và hành vi.
```

Hai luồng nên dùng **thư mục output tách biệt**, tránh tranh chấp file. Nếu cả hai phải cùng sử dụng một dependency cache, cần hiểu cơ chế khóa và tính cô lập của cache.

### Giai đoạn D — Chuyển luồng chính bằng một thay đổi rõ ràng

Khi đạt tiêu chí tương đương, cập nhật CI để công cụ mới làm **đường build chính** cho phạm vi đã chuyển. Trong khoảng chuyển tiếp, Ant có thể được giữ để rollback hoặc so sánh, nhưng cần quy định khoảng thời gian và owner chịu trách nhiệm.

Đừng để cả hai pipeline đều publish cùng một tọa độ artifact vào repository phát hành mà không có cơ chế phối hợp; như vậy có thể ghi đè hoặc tạo ra artifact không thể truy vết.

### Giai đoạn E — Thu hẹp hoặc kết thúc phần Ant

Đánh giá những target Ant còn lại:

- Có caller nào còn sử dụng không?
- Có artifact nào chỉ Ant tạo được không?
- Đã chuyển toàn bộ test/manifest/resource bắt buộc chưa?
- CI và developer có thể chạy một lệnh build mới thống nhất chưa?
- Có cần giữ Ant cho mục đích hỗ trợ legacy có chủ đích không?

Chỉ xóa file build/target khi đã xác nhận không còn dependency cần thiết. Nếu giữ Ant trong mô hình hybrid, cần ghi rõ lý do, phạm vi, owner và thời điểm đánh giá lại.

## 10. Thiết lập cổng nghiệm thu để kết thúc chuyển đổi

Một dự án chuyển đổi nên có **định nghĩa hoàn tất (Definition of Done)** theo từng phạm vi. Ví dụ:

| Nhóm điều kiện | Cách chứng minh | Trạng thái |
| --- | --- | --- |
| Phạm vi chức năng đã đủ | Bản đồ target → task mới; không còn bước bắt buộc bị bỏ sót | Bắt buộc |
| Clean build từ checkout mới | Chạy trên runner chuẩn với toolchain đã chỉ định | Bắt buộc |
| Dependency được quản lý | Có nguồn và phiên bản xác định, không cần JAR cục bộ bí ẩn | Bắt buộc |
| Compile/test đúng | Báo cáo test, release bytecode, các chế độ lỗi được xử lý | Bắt buộc |
| Artifact đáp ứng hợp đồng | Kiểm tra tên, nội dung, API, manifest và chức năng | Bắt buộc |
| CI dùng đúng đường mới | Job/target chính rõ, log và exit code phản ánh lỗi | Bắt buộc |
| Triển khai/rollback | Quy trình rollback được xác định cho phần có ảnh hưởng phát hành | Tùy mức độ rủi ro, thường bắt buộc với release |
| Caller Ant cũ | Đã di chuyển hoặc có wrapper thời hạn cụ thể | Bắt buộc với phạm vi retire Ant |
| Tài liệu và owner | Có hướng dẫn local/CI, biết ai bảo trì toolchain mới | Bắt buộc |
| Theo dõi sau chuyển | Quan sát lỗi, thời gian build, deployment trong thời gian đánh giá | Nên có |

Trong thực tế, nhóm có thể bổ sung gate về bảo mật, SBOM, chữ ký artifact, giấy phép dependency, vulnerability scan hoặc kiểm thử hiệu năng nếu đã là hợp đồng hiện hành. Chỉ vì thay Ant bằng công cụ mới không có nghĩa các nghĩa vụ này tự động được đáp ứng.

### 10.1. Phân biệt hoàn tất “chuyển phạm vi” và “retire Ant”

**Hoàn tất chuyển phạm vi:** module `core-api` đã chuyển sang Maven/Gradle, build và test đầy đủ, mọi caller đã dùng đường mới. Repository vẫn còn Ant cho `legacy-packager`; việc này không làm thất bại mục tiêu chuyển `core-api` nếu phạm vi đã xác định rõ.

**Retire Ant toàn bộ:** không còn target Ant nào trong critical path của build/test/release, mọi custom task cần thiết đã được thay hoặc chuyển thành component khác, các caller đã được cập nhật, không còn cần tài liệu/cài đặt Ant cho đường build được hỗ trợ. Khi đó mới có cơ sở xóa hoặc archive `build.xml` tương ứng.

**Quyết định giữ hybrid:** Ant vẫn tạo artifact legacy theo hợp đồng, các module mới chạy bằng công cụ khác, CI có bước phối hợp rõ và dự án kết thúc với mô hình vận hành hỗn hợp được chấp nhận. Khi ấy không nên cố xóa Ant chỉ để “đạt 100% chuyển đổi”.

### 10.2. Không kết thúc chỉ dựa trên “CI xanh”

CI xanh có thể chưa đủ nếu:

- Target `verify` không thực sự chạy test bắt buộc.
- Công cụ mới tạo JAR nhưng thiếu resource hoặc manifest.
- Script `<exec>` không truyền lỗi ra build.
- CI dùng JDK mới nhưng production dùng JVM cũ hơn.
- Một nhánh codegen hoặc packaging chỉ chạy trong release mà chưa được thử.
- Cách chạy local phụ thuộc file mà developer phải tự tạo thủ công.
- Một job ngoài repository vẫn gọi tên target Ant đã bị xóa.

Một gate nghiệm thu tốt kiểm tra **phạm vi được cam kết** và mô tả bằng chứng. Nếu một điều kiện không thể kiểm tra, hãy ghi rõ rủi ro còn lại và chủ sở hữu trước khi tuyên bố hoàn tất.

## 11. Giảm rủi ro khi duy trì hai hệ thống trong giai đoạn chuyển tiếp

Chạy Ant và công cụ mới cùng lúc thường tạo ra các rủi ro riêng.

### 11.1. Chỉ một nơi quyết định phiên bản dependency

Nếu Ant dùng `lib/example-api-1.2.jar` còn Gradle/Maven phân giải `example-api:1.4`, hai pipeline có thể tạo bytecode hoặc hành vi khác nhau. Cần lập danh sách dependency và phiên bản, sau đó xác định hệ thống nào là nguồn cấu hình chính trong từng giai đoạn.

Ví dụ:

| Dependency | Ant legacy | Công cụ mới | Hành động |
| --- | --- | --- | --- |
| API nội bộ | JAR ở `lib/` | Dependency từ repository nội bộ | Chốt version và cách kiểm tra checksum |
| Logging library | JAR local | Dependency được khai báo | Kiểm tra xung đột phiên bản/transitive |
| Test framework | Ant task và JAR cũ | Plugin/test runner mới | So test được phát hiện, skip/failure |
| Java platform | `source/target` | Toolchain/`release` | Chuẩn hóa Java runtime mục tiêu |

### 11.2. Không cùng ghi vào một output

Nếu Ant và Gradle cùng ghi `build/classes`, một lần build có thể lấy class cũ từ công cụ còn lại. Dùng thư mục riêng:

```text
build/ant-classes/
build/ant-dist/
build/gradle-output/       # Hoặc thư mục chuẩn do Gradle quản lý
```

Nếu công cụ mới mặc định dùng một thư mục như `build/`, tránh đặt output của Ant trùng các thư mục bên trong mà tool mới dọn dẹp. Chỉ đưa artifact từ một vùng sang vùng khác qua một bước giao nhận có owner.

### 11.3. Không cho hai luồng cùng publish

Trong shadow build, nên **chạy và lưu artifact để so**, nhưng chỉ đường build được chọn mới có quyền publish/deploy. Việc cả hai cùng phát hành phiên bản `1.0.0` có thể khiến repository chứa artifact không biết thuộc quy trình nào.

Khi chuyển quyền phát hành từ Ant sang công cụ mới, cần có một mốc cutover rõ ràng và cơ chế xác định artifact của commit/release nào được phát hành.

### 11.4. Tránh vòng gọi và fail giả

Một rủi ro điều phối:

```text
Ant target verify → gọi Gradle verify
Gradle verify     → gọi Ant target verify
```

Đây là vòng gọi vô hạn theo logic. Với mô hình kết hợp, hãy chọn một chiều điều phối hoặc để CI điều khiển từng bước.

Ngoài ra, nếu Ant gọi một chương trình qua `<exec>`, cần đảm bảo mã thoát khác 0 làm bước build thất bại đúng lúc:

```xml
<exec executable="mvn"
      dir="modern-module"
      failonerror="true">
    <arg value="-B"/>
    <arg value="verify"/>
</exec>
```

Ví dụ này giả định đã cài Maven trong `PATH` và `modern-module` là dự án Maven. Chạy trên Windows/Linux cần kiểm tra cách tìm launcher trong từng môi trường. `failonerror="true"` ở đây hữu ích để Ant không báo thành công khi tiến trình con trả mã lỗi.

## 12. Minh họa một đường chuyển đổi theo mô-đun

Giả sử dự án có:

```text
repository/
├── legacy-generator/
│   └── build.xml             # Sinh Java source theo định dạng cũ
├── service/
│   └── build.gradle          # Biên dịch, kiểm thử, đóng gói
└── ci/
    └── pipeline-definition
```

Ant hiện tạo ra source Java cần thiết cho `service`. Nếu tính năng generator được sử dụng ổn định và khó thay thế, có thể giữ Ant như một bước độc lập.

### 12.1. Ant giữ vai trò sinh mã

Ví dụ `legacy-generator/build.xml` minh họa hợp đồng đầu ra. Phần tạo mã thực tế có thể là custom task riêng, nên ví dụ dùng một file mẫu đã tồn tại để trình bày cách giao artifact:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="legacy-generator" default="generate-sources" basedir=".">
    <property name="input.file" location="templates/Generated.java"/>
    <property name="output.dir" location="../generated/legacy"/>

    <target name="check-input">
        <available file="${input.file}"
                   type="file"
                   property="input.exists"/>
        <fail unless="input.exists"
              message="[check-input] Thiếu templates/Generated.java"/>
    </target>

    <target name="generate-sources" depends="check-input">
        <mkdir dir="${output.dir}"/>
        <copy file="${input.file}"
              tofile="${output.dir}/Generated.java"
              overwrite="true"/>
        <echo level="info"
              message="[generate-sources] Đã tạo ${output.dir}/Generated.java"/>
    </target>
</project>
```

Trong ví dụ này, `templates/Generated.java` phải tồn tại và là file Java phù hợp với source set mà công cụ mới sử dụng. Task `<copy>` chỉ minh họa giao nhận, **không phải một trình sinh mã thực tế**. Một generator thực phải ghi đầu ra đúng schema/tên package và trả lỗi rõ khi không tạo được.

Để tái lập, trước khi chạy nên làm sạch riêng output `generated/legacy` theo hợp đồng của bước generator; tránh xóa rộng vào thư mục do công cụ mới sở hữu.

### 12.2. CI điều phối từng bước

Pseudo-pipeline:

```text
checkout đúng commit
  ↓
setup JDK và Ant đã thống nhất
  ↓
ant -f legacy-generator/build.xml generate-sources
  ↓
kiểm tra generated/legacy/Generated.java và các điều kiện đầu ra
  ↓
setup Gradle/Maven theo version đã chốt
  ↓
chạy test + package của service
  ↓
kiểm tra artifact, report, smoke test
  ↓
chỉ publish artifact được chọn từ công cụ mới
```

Tại đây, Ant có một trách nhiệm rõ: tạo source từ input đã xác định. Công cụ mới sở hữu compile/test/package. Nếu sau này thay generator, nhóm chỉ cần thay bước đó và kiểm chứng interface đầu ra; không phải sửa toàn bộ chuỗi test/packaging.

### 12.3. Khi nào mô hình này có thể kết thúc?

Có hai câu trả lời hợp lệ:

- **Giữ hybrid:** generator Ant vẫn là thành phần được hỗ trợ, có owner và test; CI chính dùng cả Ant và công cụ mới. Dự án chuyển đổi phần `service` đã hoàn tất.
- **Retire Ant:** generator được thay bằng tác vụ khác với cùng hợp đồng đầu ra; các caller không còn gọi Ant; lệnh build mới chạy từ clean checkout và đủ gate. Khi đó có thể ngừng phát hành/cài đặt Ant trong môi trường build của phạm vi này.

## 13. Hồ sơ quyết định kỹ thuật nên lưu gì?

Quyết định cuối cần đủ rõ để nhóm khác có thể hiểu vì sao một công cụ được giữ hay bỏ. Có thể viết ngắn theo mẫu:

```markdown
# Quyết định build cho module service

## Bối cảnh
- Ant hiện xử lý những target nào?
- Những vấn đề đã được đo hoặc ghi nhận là gì?

## Phạm vi
- Module/artifact/CI job nào thuộc quyết định?
- Phần nào không thuộc phạm vi?

## Phương án xem xét
- Giữ Ant
- Kết hợp Ant với công cụ mới
- Chuyển hoàn toàn

## Tiêu chí và bằng chứng
- Tính đúng của artifact
- Test và compatibility
- Toolchain và dependency
- Chi phí vận hành
- Rủi ro phát hành

## Quyết định
- Phương án được chọn
- Lý do và những đánh đổi
- Ranh giới owner/đầu ra nếu hybrid

## Kiểm chứng và mốc đánh giá lại
- Lệnh local/CI chuẩn
- Gate hoàn tất
- Người chịu trách nhiệm
- Rủi ro chưa giải quyết
```

Mẫu này tránh quyết định mơ hồ như “giữ Ant vì quen tay” hoặc “dùng Gradle vì hiện đại”. Nó cũng giúp phân biệt **đã quyết định giữ hybrid** với **đang chuyển đổi dở dang và chưa có người chịu trách nhiệm**.

## 14. Các tín hiệu cần xem xét lại quyết định

Ngay cả khi đã chọn giữ Ant, quyết định có thể cần xem lại khi:

- Nâng phiên bản Java khiến custom task không còn hoạt động.
- Dependency được quản lý bằng thao tác thủ công gây lỗi bảo trì lặp lại.
- Mô-đun mới tăng nhanh và việc phối hợp build khó kiểm soát.
- CI phải dùng image hoặc runtime không còn được hỗ trợ chỉ vì một bước Ant.
- Có thay đổi yêu cầu artifact (ví dụ SBOM, chữ ký, provenance hoặc policy) mà pipeline hiện tại khó đáp ứng.
- Người duy nhất hiểu custom task rời nhóm và không có tài liệu/chuyển giao.
- Mục tiêu hiệu suất hoặc time-to-feedback không đạt dù đã tối ưu những điểm rõ ràng.

Ngược lại, sau khi đã chọn chuyển đổi, cũng nên đánh giá lại nếu bằng chứng cho thấy rủi ro cao hơn lợi ích dự tính. Có thể thu hẹp phạm vi, chuyển mô-đun độc lập trước hoặc chốt trạng thái hybrid ổn định.

Một quyết định kỹ thuật có chất lượng luôn có **điều kiện để đánh giá lại**, không cần được xem là vĩnh viễn.

## 15. Bài thực hành lập quyết định cho ba tình huống

### Tình huống A — Ứng dụng legacy ít thay đổi

Ứng dụng Java 8 có khoảng mười target Ant, một custom task đóng gói và ít dependency. CI clean build thành công, có test và artifact được phát hành ổn định. Công ty chưa có nhu cầu thay đổi kiến trúc.

**Bài tập:**

1. Lập danh sách chi phí/rủi ro nếu chuyển sang Maven/Gradle.
2. Xác định những điểm cần cải thiện trong Ant mà không phải đổi công cụ.
3. Chọn các gate tối thiểu để xác nhận quyết định giữ Ant.
4. Xác định điều kiện buộc xem lại (chẳng hạn cần nâng runtime hoặc custom task không còn hỗ trợ).

Gợi ý: quyết định giữ có thể hợp lý nếu bằng chứng cho thấy lợi ích chuyển thấp, nhưng phải bảo đảm công cụ hiện tại vẫn vận hành và bảo trì được.

### Tình huống B — Repository có legacy generator và dịch vụ mới

Một Ant task sinh Java source từ mô hình cũ. Dịch vụ mới cần dependency graph, integration test và lifecycle đóng gói hiện đại.

**Bài tập:**

1. Chọn owner cho generated source, classfile, test report và artifact cuối.
2. Thiết kế pipeline sao cho không cùng ghi một output.
3. Chọn hướng điều phối: CI gọi hai lệnh hay một công cụ làm orchestrator.
4. Đặt điều kiện nào phải thỏa trước khi dịch vụ mới được publish.
5. Đề xuất tiêu chí để quyết định giữ hybrid lâu dài hoặc tiếp tục thay generator.

Gợi ý: kết hợp thường phù hợp nếu interface generator đã rõ và giữ nó giảm rủi ro chuyển đổi.

### Tình huống C — Hầu hết build đã chuyển sang công cụ mới

Gradle đã compile, test, package và publish. Tệp `build.xml` chỉ còn một target gọi `gradle build`; tuy vậy một script CI cũ vẫn chạy `ant release`.

**Bài tập:**

1. Liệt kê các caller còn sử dụng Ant.
2. Xác định Ant có còn sở hữu output hoặc chức năng nào độc lập không.
3. Lập kế hoạch cập nhật script CI sang điểm vào chính mới.
4. Chọn gate nghiệm thu để xóa wrapper và ngừng yêu cầu Ant trên runner.
5. Đề xuất cách rollback trong giai đoạn cutover nếu release có lỗi.

Gợi ý: có cơ sở retire Ant khi toàn bộ caller và tác vụ bắt buộc đã chuyển, có bằng chứng build mới tương đương và cơ chế phát hành hoạt động đúng.

## 16. Những sai lầm thường gặp khi đưa ra kết luận

| Sai lầm | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| “Tool mới luôn tốt hơn” | Không xét rủi ro của custom task, artifact và hệ thống legacy | Chọn theo mục tiêu và bằng chứng |
| “Ant còn build được thì giữ mãi” | Bỏ qua khả năng tái lập, nhân sự bảo trì và toolchain hết hỗ trợ | Đặt gate vận hành và chu kỳ xem lại |
| Chạy hai tool cùng output | Có thể trộn class, resource, file cũ | Chỉ định owner cho từng thư mục |
| Hai pipeline đều publish một phiên bản | Không biết artifact nào là bản phát hành thật | Một pipeline có quyền publish tại mỗi thời điểm |
| Chỉ so exit code 0 | Có thể mất test hoặc resource mà build vẫn xanh | So tập công việc, report, artifact, smoke test |
| Bỏ Ant trước khi cập nhật external caller | CI, script và release cũ gãy | Kiểm kê và chuyển caller có kiểm soát |
| Giữ Ant wrapper không thời hạn | Tăng chi phí và che giấu điểm vào thật | Ghi mục đích, owner, mốc loại bỏ hoặc xác nhận hybrid |
| Dùng tên target giống nhau và cho rằng tương đương | `verify` của hai tool có thể chạy các tác vụ khác nhau | Ánh xạ hành vi thực tế của từng task |
| Khẳng định artifact khác hash là chức năng khác | ZIP/JAR có thể khác timestamp/metadata | So manifest, class, resource, test và yêu cầu byte reproducibility |
| Quên runtime mục tiêu | Compile pass nhưng deploy lỗi bytecode/Classpath | Smoke/integration test trên runtime được hỗ trợ |

## 17. Kết luận

Ba kết quả **giữ Ant, kết hợp công cụ hoặc kết thúc chuyển đổi** đều có thể đúng. Tiêu chí quyết định là mức độ đáp ứng yêu cầu, chi phí bảo trì, khả năng tái lập, rủi ro thay đổi và bằng chứng bảo toàn sản phẩm.

Giữ Ant khi build hiện tại đáp ứng yêu cầu với chi phí hợp lý và có người chịu trách nhiệm. Kết hợp khi các phần legacy và mới có ranh giới input/output rõ, không trùng owner và không tạo vòng gọi. Chỉ retire Ant khỏi phạm vi chuyển đổi khi mọi công việc bắt buộc, caller, test và artifact đã chuyển, CI chạy đúng đường mới và điều kiện nghiệm thu được xác nhận.

Một dự án chuyển đổi có thể kết thúc thành công với **mô hình hybrid được duy trì có chủ đích**. Điều quan trọng là quyết định được ghi nhận, các giới hạn vận hành minh bạch và đường build chính có thể thực thi, kiểm chứng và bảo trì bởi cả nhóm.
