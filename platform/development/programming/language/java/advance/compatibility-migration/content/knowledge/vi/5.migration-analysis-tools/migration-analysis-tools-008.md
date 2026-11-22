# So sánh API công khai giữa hai bản phát hành bằng japicmp hoặc Revapi

Khi phát hành phiên bản mới của một thư viện Java, cần biết những thành phần API nào đã được thêm, thay đổi hoặc loại bỏ so với bản phát hành trước. Một thay đổi nhỏ trong source code có thể làm ứng dụng đã biên dịch trước đó không còn chạy được, khiến mã nguồn consumer không biên dịch lại được hoặc làm thay đổi hành vi mà consumer đang dựa vào. So sánh API giữa hai bản phát hành giúp phát hiện sớm các thay đổi này trước khi phát hành.

`japicmp` và `Revapi` là hai công cụ thường dùng để phân tích khác biệt API của thư viện Java. Chúng đọc artifact đã biên dịch của phiên bản cũ và phiên bản mới, xác định các thành phần API thay đổi và tạo báo cáo để nhóm phát triển đánh giá. Có thể đưa bước so sánh vào CI để mỗi thay đổi API đều được xem xét trước khi merge hoặc release.

## 1. Xác định API công khai cần bảo vệ

Trước khi chạy công cụ, cần xác định chính xác “API công khai” của thư viện. API là hợp đồng mà consumer được phép sử dụng và có thể dựa vào giữa các lần phát hành.

Với một thư viện Java, bề mặt API thường bao gồm:

- Package và class/interface/enum/record được công bố.
- Constructor, method và field có thể truy cập từ consumer.
- Kiểu tham số, kiểu trả về, generic signature và checked exception.
- Quan hệ kế thừa, interface được triển khai và modifier như `static`, `final`, `abstract`.
- Annotation hoặc metadata có ý nghĩa đối với compiler, framework hay consumer.
- Các kiểu lồng nhau, nested class, annotation type và enum constant.
- Module/package được export nếu thư viện sử dụng Java Platform Module System (JPMS).

Không phải mọi class có modifier `public` đều là API công khai có cam kết ổn định. Một class `public` nằm trong package nội bộ không được export bởi module có thể không truy cập được từ module consumer. Ngược lại, một package được export và được tài liệu hóa rõ ràng thường là một phần của bề mặt API cần bảo vệ.

Nên phân biệt:

- **Public API:** phần thư viện chủ động công bố cho consumer.
- **Protected API:** thành phần dành cho lớp mở rộng hoặc subclass; có thể là một phần của hợp đồng mở rộng.
- **Internal implementation:** class/package phục vụ triển khai nội bộ, không được cam kết cho consumer.
- **SPI (Service Provider Interface):** API dành cho bên thứ ba cung cấp implementation hoặc plugin; thay đổi ở đây có thể ảnh hưởng nhiều hơn API gọi thông thường.

Phạm vi so sánh phải nhất quán giữa hai bản phát hành. Nếu bản cũ được lọc chỉ còn package `com.example.publicapi` nhưng bản mới lại quét toàn bộ artifact, báo cáo có thể chứa nhiều khác biệt không thuộc phạm vi cần kiểm tra.

## 2. Chuẩn bị artifact cũ và mới

Hai công cụ so sánh artifact, vì vậy cần chuẩn bị đúng JAR đại diện cho hai bản phát hành.

- **Artifact cũ:** bản đã phát hành hoặc bản baseline đã được phê duyệt, ví dụ `library-1.4.0.jar`.
- **Artifact mới:** JAR được build từ commit hoặc tag đang chuẩn bị phát hành, ví dụ `library-1.5.0-SNAPSHOT.jar`.
- **Metadata:** group, artifact, version, classifier, module name và nguồn tải artifact.
- **Dependencies:** các dependency cần thiết để công cụ phân tích kiểu cha, interface hoặc kiểu được tham chiếu.
- **Scope:** package/module nào thuộc API cần so sánh, access level nào được tính và thành phần nào bị loại trừ có lý do.

Ưu tiên lấy artifact cũ từ repository phát hành nội bộ hoặc kho artifact đã xác minh. Không nên lấy source code cũ từ một nhánh đang tiếp tục thay đổi rồi build lại bằng toolchain mới nếu mục tiêu là so sánh đúng những gì consumer đã nhận. Artifact đã phát hành là bằng chứng tốt hơn cho hợp đồng thực tế.

Artifact mới phải được build từ cùng quy trình release mà tổ chức dự định sử dụng. Nếu JAR được tạo từ một task khác, thiếu generated classes, module descriptor, annotation processing hoặc bytecode enhancement so với artifact phát hành thật, kết quả so sánh có thể không phản ánh sản phẩm cuối cùng.

Trước khi chạy công cụ, kiểm tra checksum, version và nội dung JAR. Không so sánh nhầm hai file cùng tên nhưng đến từ môi trường hoặc commit khác nhau. Với multi-module library, so sánh từng artifact có API độc lập; đồng thời ghi quan hệ giữa các module nếu public API của module này tham chiếu kiểu được định nghĩa ở module khác.

## 3. Japicmp hoạt động như thế nào?

`japicmp` phân tích các class đã biên dịch trong hai phiên bản thư viện và báo cáo các khác biệt có liên quan đến khả năng tương thích. Công cụ tập trung vào Java binary API, tức các kiểu và thành viên mà bytecode của consumer tham chiếu tới.

Những thay đổi thường được phát hiện gồm:

- Class, interface, enum hoặc method bị xóa.
- Class hoặc thành viên bị giảm mức truy cập.
- Kiểu trả về hoặc kiểu tham số thay đổi.
- Constructor, field hoặc method được thêm hoặc thay đổi.
- Thay đổi modifier, quan hệ kế thừa hoặc interface được triển khai.
- Một số thay đổi generic signature và cấu trúc kiểu được công cụ nhận diện.

Japicmp phân loại mức độ ảnh hưởng tương thích dựa trên cấu trúc bytecode và quy tắc tương thích Java. Điều này giúp reviewer tập trung vào thay đổi có thể phá vỡ consumer thay vì phải đọc toàn bộ diff của source code.

### 3.1. So sánh hai JAR bằng CLI

Sau khi lấy được bản phân phối CLI phù hợp của japicmp, có thể so sánh hai artifact trực tiếp. Ví dụ sau dùng tên file minh họa; thay bằng đường dẫn thực tế và phiên bản japicmp đã được tổ chức phê duyệt.

~~~bash
java -jar japicmp-<version>-jar-with-dependencies.jar \
  --old target/library-1.4.0.jar \
  --new target/library-1.5.0.jar \
  --only-modified \
  --access-modifier public \
  --html-file target/api-compatibility.html
~~~

Ý nghĩa các tham số chính:

- `--old`: artifact baseline của phiên bản cũ.
- `--new`: artifact của phiên bản mới cần đánh giá.
- `--only-modified`: tập trung vào các thành phần có khác biệt thay vì liệt kê toàn bộ API không đổi.
- `--access-modifier`: giới hạn mức truy cập được đưa vào so sánh. Chọn mức phù hợp với hợp đồng của thư viện; nếu protected API hoặc SPI là cam kết công khai, cần đưa chúng vào phạm vi.
- `--html-file`: xuất báo cáo HTML để reviewer đọc và lưu làm artifact CI.

Tên và cách đóng gói file CLI có thể khác theo bản japicmp được chọn. Hãy kiểm tra `--help` của đúng phiên bản công cụ để xác nhận các option trước khi đưa lệnh vào pipeline. Có thể xuất XML nếu quy trình cần máy đọc báo cáo hoặc tích hợp kết quả với hệ thống khác.

### 3.2. Đọc kết quả japicmp

Kết quả thường chia các thành phần thành nhóm như mới, bị xóa, thay đổi và không đổi; các thay đổi còn được đánh giá theo khả năng tương thích. Khi đọc báo cáo:

1. Xác nhận đúng artifact cũ và mới.
2. Xem package/class nào bị tác động.
3. Xem chính xác thành viên nào thay đổi: method, constructor, field, generic type hoặc modifier.
4. Đọc phân loại tương thích mà japicmp báo cáo.
5. Đối chiếu với cách consumer thực tế gọi API.
6. Xác định thay đổi nào có chủ đích, thay đổi nào vô tình và hành động cần thiết.

Ví dụ, nếu method `public Result find(String id)` bị xóa, bytecode consumer cũ có thể không liên kết được với JAR mới và gặp lỗi `NoSuchMethodError` khi đường chạy gọi method đó. Nếu method được đổi từ `public` thành `protected`, consumer không nằm trong package/subclass phù hợp có thể không còn truy cập được. Báo cáo giúp chỉ ra thay đổi cấu trúc; kiểm thử với consumer cũ xác nhận tác động trong ứng dụng thực tế.

### 3.3. Tích hợp japicmp vào quy trình build

Japicmp có thể được gọi từ Maven plugin, Gradle plugin phù hợp hoặc CLI trong CI. Dù dùng cách nào, pipeline cần cung cấp rõ artifact cũ và mới, phạm vi API, phiên bản công cụ và vị trí báo cáo.

Một pipeline điển hình:

~~~text
Build artifact mới
       |
       v
Lấy artifact baseline đã phát hành
       |
       v
Chạy japicmp với cùng API scope
       |
       v
Lưu HTML/XML report
       |
       v
Phân loại thay đổi và kiểm tra policy
       |
       v
Review / fail build theo ngưỡng đã thống nhất
~~~

Không nên tự động fail mọi khác biệt. Một method mới thường là thay đổi được chấp nhận; một method bị xóa có thể là breaking change; một thay đổi nội bộ nằm ngoài public API có thể không cần chặn release. Chính sách cần dựa trên mức độ tương thích, SemVer và hợp đồng mà dự án cam kết.

## 4. Revapi hoạt động như thế nào?

`Revapi` là framework phân tích khác biệt API có thể mở rộng bằng analyzer, filter, transform và reporter. Với Java, phần phân tích Java API thường được cung cấp bởi extension `revapi-java`. Revapi so sánh API của artifact cũ và mới, sau đó tạo các phát hiện có mã loại thay đổi, mức độ và thông tin vị trí.

Điểm hữu ích của Revapi là khả năng cấu hình sâu cách nhận diện API và cách xử lý phát hiện:

- Chỉ phân tích package hoặc thành phần thuộc API công khai.
- Loại trừ thành phần nội bộ có lý do rõ ràng.
- Điều chỉnh mức độ nghiêm trọng/criticality theo chính sách dự án.
- Bỏ qua một phát hiện đã được chấp thuận có phạm vi cụ thể.
- Chuyển đổi hoặc chuẩn hóa một số phát hiện trước khi báo cáo.
- Dùng reporter khác nhau để tạo output phù hợp cho developer hoặc CI.

Revapi không nên được xem là một danh sách cảnh báo chung. Nó tạo ra các phát hiện có cấu trúc để nhóm quyết định thay đổi nào được chấp nhận, thay đổi nào phải sửa và thay đổi nào cần giải trình.

### 4.1. Cấu hình Revapi cho Java

Trong Maven, cách tích hợp phổ biến là dùng `revapi-maven-plugin` và extension phân tích Java `revapi-java`. Plugin được cấu hình để biết artifact cũ và artifact mới, sau đó chạy goal kiểm tra trong lifecycle thích hợp, thường là giai đoạn `verify` hoặc một bước kiểm tra release riêng.

Một cấu hình có cấu trúc khái quát như sau; phiên bản plugin và Java analyzer phải được chọn theo ma trận tương thích của dự án:

~~~xml
<plugin>
    <groupId>org.revapi</groupId>
    <artifactId>revapi-maven-plugin</artifactId>
    <version>${revapi.maven.plugin.version}</version>
    <dependencies>
        <dependency>
            <groupId>org.revapi</groupId>
            <artifactId>revapi-java</artifactId>
            <version>${revapi.java.version}</version>
        </dependency>
    </dependencies>
    <executions>
        <execution>
            <id>check-public-api</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là phần khung tích hợp plugin và Java analyzer, không phải một cấu hình hoàn chỉnh cho mọi dự án. Cần cấu hình thêm artifact baseline/target, phạm vi API, analysis configuration và reporter theo đúng tài liệu của phiên bản `revapi-maven-plugin` đang dùng. Không sao chép cấu hình từ một phiên bản plugin khác mà chưa kiểm tra tên parameter và schema tương ứng.

Với dự án Gradle, có thể tích hợp qua task hoặc plugin hỗ trợ Revapi nếu tổ chức đã chọn và kiểm chứng phiên bản đó. Nếu không có plugin phù hợp, có thể chạy công cụ trong một bước CI riêng và truyền artifact cũ/mới theo giao diện được công cụ hỗ trợ. Điều quan trọng là không để cách gọi công cụ làm thay đổi artifact đang được phát hành.

### 4.2. Filter và phạm vi API

Filter giúp Revapi chỉ phân tích những package hoặc thành phần thuộc hợp đồng. Ví dụ, thư viện có package public API và package implementation:

~~~text
com.example.payment.api
com.example.payment.spi
com.example.payment.internal
~~~

Nhóm có thể quyết định `api` là public API, `spi` là extension contract cần kiểm tra riêng, còn `internal` không được cam kết cho consumer. Cách phân loại phải dựa vào tài liệu sản phẩm, module exports và cách consumer được phép sử dụng; không nên chỉ dựa vào tên package.

Filter quá rộng tạo nhiều nhiễu, khiến reviewer bỏ qua phát hiện quan trọng. Filter quá hẹp lại che mất breaking change. Mỗi quy tắc include/exclude cần có owner và lý do, đồng thời được áp dụng giống nhau cho mọi lần so sánh.

### 4.3. Ignore có kiểm soát

Revapi hỗ trợ cấu hình các phát hiện được bỏ qua hoặc được xử lý theo chính sách riêng. Đây là công cụ hữu ích khi một thay đổi đã được đánh giá và chấp thuận, nhưng cũng dễ làm mất cảnh báo nếu dùng quá rộng.

Khi thêm ignore:

- Chỉ nhắm tới đúng API element và loại phát hiện cần bỏ qua.
- Ghi lý do nghiệp vụ/kỹ thuật và người chấp thuận.
- Nếu có thể, giới hạn theo phiên bản hoặc thời hạn.
- Không ignore toàn bộ nhóm như “mọi method bị xóa” chỉ để CI xanh.
- Review lại ignore khi phát hành phiên bản kế tiếp.

Một thay đổi breaking có thể được chấp thuận trong major release, nhưng cần ghi nhận rõ trong release notes và migration guide cho consumer. Ignore trong công cụ chỉ thay đổi cách báo cáo hoặc chặn build; nó không làm thay đổi thực tế hợp đồng.

## 5. So sánh japicmp và Revapi

Hai công cụ cùng hỗ trợ phát hiện thay đổi API giữa artifact Java, nhưng có cách tiếp cận khác nhau.

| Tiêu chí | japicmp | Revapi |
|---|---|---|
| Trọng tâm | So sánh binary API Java | Framework phân tích API có thể mở rộng |
| Cách dùng | CLI và tích hợp Maven/Gradle tùy môi trường | Plugin Maven, extension analyzer và tích hợp CI |
| Báo cáo | Danh sách thay đổi và phân loại tương thích | Phát hiện có mã, mức độ, filter, transform và reporter |
| Tùy chỉnh phạm vi | Tham số truy cập và lọc theo khả năng công cụ | Cơ chế filter/extension cấu hình sâu |
| Chính sách | Phù hợp kiểm tra binary compatibility và ngưỡng breaking | Phù hợp policy API chi tiết, ignore và xử lý phát hiện |
| Phù hợp khi | Cần báo cáo nhanh, trực tiếp về khác biệt Java binary API | Cần quản trị API evolution theo quy tắc riêng và báo cáo mở rộng |

Chọn japicmp khi mục tiêu chính là so sánh nhanh hai JAR và phát hiện thay đổi binary API. Chọn Revapi khi cần hệ thống phân tích có khả năng cấu hình filter, mức độ, ngoại lệ và reporter theo chính sách tổ chức. Hai công cụ không loại trừ nhau; một dự án có thể dùng một công cụ chính và dùng công cụ còn lại khi có nhu cầu bổ sung, nhưng cần tránh tạo hai báo cáo trùng lặp mà không có owner xử lý.

Không công cụ nào tự quyết định một thay đổi có được chấp nhận về mặt sản phẩm hay không. Công cụ cung cấp bằng chứng cấu trúc; nhóm phát triển cần đối chiếu hợp đồng, SemVer, consumer thực tế và kế hoạch migration.

## 6. Hiểu các loại tương thích mà báo cáo đề cập

### 6.1. Binary compatibility

Binary compatibility trả lời liệu bytecode đã biên dịch dựa trên phiên bản cũ có thể liên kết với phiên bản mới mà không cần biên dịch lại hay không.

Ví dụ, consumer đã biên dịch gọi `PaymentClient.charge(String)`. Nếu phiên bản mới xóa method này, runtime có thể ném `NoSuchMethodError` khi lời gọi được thực thi. Nếu class hoặc interface thay đổi cấu trúc theo cách không tương thích, có thể xuất hiện các lỗi liên kết khác.

Đây là nhóm thay đổi mà công cụ so sánh bytecode như japicmp đặc biệt hữu ích để phát hiện. Tuy nhiên, kết quả còn phụ thuộc vào phạm vi class, dependency và cách công cụ phân loại thay đổi.

### 6.2. Source compatibility

Source compatibility trả lời liệu source code consumer cũ có thể biên dịch lại với thư viện mới mà không cần sửa hay không.

Ví dụ, thêm một overload có thể khiến lời gọi vốn rõ ràng trở nên mơ hồ khi biên dịch lại. Thêm phương thức abstract vào interface có thể khiến class triển khai cũ không biên dịch được. Một thay đổi có thể không phá binary compatibility nhưng vẫn phá source compatibility.

API diff tool có thể phát hiện nhiều thay đổi cấu trúc có khả năng gây lỗi source, nhưng không thay thế việc biên dịch consumer mẫu với compiler đích.

### 6.3. Behavioral compatibility

Behavioral compatibility liên quan đến kết quả và tác dụng quan sát được. Chữ ký method không đổi nhưng method có thể đổi quy tắc validation, giá trị mặc định, thứ tự kết quả, exception hoặc tác dụng phụ.

Ví dụ, `findById` trước đây trả về `Optional.empty()` khi không có dữ liệu nhưng phiên bản mới ném exception. API diff có thể không phát hiện khác biệt này vì chữ ký vẫn giữ nguyên. Cần contract test, integration test và kiểm thử hành vi.

### 6.4. Compatibility của module và runtime

Với JPMS, package export, `requires`, `uses` và `provides` có thể ảnh hưởng khả năng truy cập API và discovery service. Với runtime, JDK baseline, native library, agent, reflection, serialization và cấu hình bảo mật có thể gây lỗi mà một báo cáo API class-level không thể kết luận.

Do đó, API diff là một cổng kiểm tra quan trọng nhưng chỉ là một phần trong chiến lược tương thích tổng thể.

## 7. Diễn giải thay đổi thường gặp

| Thay đổi | Rủi ro điển hình | Hành động đánh giá |
|---|---|---|
| Xóa public class hoặc method | Consumer cũ có thể không biên dịch hoặc lỗi liên kết | Xác định consumer sử dụng; giữ API cũ hoặc phát hành major version |
| Giảm visibility `public` xuống `protected`/package-private | Consumer bên ngoài mất quyền truy cập | Kiểm tra phạm vi consumer và hợp đồng công khai |
| Đổi kiểu tham số hoặc kiểu trả về | Thay đổi descriptor hoặc source signature | Kiểm tra binary/source compatibility và cung cấp overload/adapter nếu phù hợp |
| Thêm abstract method vào interface | Implementation hiện tại có thể không biên dịch hoặc không thực hiện được method | Cân nhắc default method hoặc interface mới; kiểm thử implementor |
| Thêm method overload | Có thể làm lời gọi source cũ mơ hồ | Biên dịch consumer cũ với phiên bản mới |
| Thêm class/method mới | Thường là mở rộng API | Kiểm tra xung đột tên, semantics và dependency |
| Thay generic signature | Có thể ảnh hưởng source, reflection và framework | Kiểm tra generic consumer, reflection và metadata |
| Thay superclass/interface | Có thể đổi contract kế thừa hoặc dispatch | Kiểm tra subclass, implementor và method resolution |
| Đổi annotation hoặc module export | Có thể ảnh hưởng framework, compiler hoặc JPMS | Kiểm tra annotation processor, runtime discovery và module consumer |

Không nên kết luận mọi thay đổi trong bảng đều luôn gây lỗi. Mức ảnh hưởng phụ thuộc vào chữ ký cụ thể, cách consumer sử dụng, JVM/linker, module system và phạm vi API được cam kết.

## 8. Thiết lập baseline và policy cho CI

Để API comparison có giá trị lâu dài, dự án cần một baseline rõ ràng. Baseline thường là artifact của bản phát hành gần nhất đã được công bố và chấp nhận, không phải một build tùy ý từ nhánh đang phát triển.

Quy trình CI có thể gồm:

1. Build artifact mới bằng quy trình release chuẩn.
2. Tải artifact baseline theo group/artifact/version từ repository đã xác minh.
3. Chạy japicmp hoặc Revapi với cùng phạm vi package, access level và cấu hình.
4. Lưu report làm artifact của pipeline và hiển thị tóm tắt trong kết quả build.
5. Áp dụng policy: cảnh báo, yêu cầu review hoặc fail build đối với loại thay đổi đã quy định.
6. Ghi nhận ngoại lệ đã được phê duyệt và liên kết tới issue/release note tương ứng.

Policy cần phù hợp với cách dự án đánh số phiên bản. Nếu dùng Semantic Versioning, thay đổi breaking thường cần major version mới; bổ sung API tương thích thường có thể thuộc minor release; sửa lỗi không làm thay đổi public contract thường thuộc patch release. Tuy nhiên, cách phân loại phải theo hợp đồng và chính sách thực tế, không chỉ dựa vào nhãn mà công cụ sinh ra.

Với pull request, có thể so sánh artifact của nhánh hiện tại với baseline của nhánh chính hoặc bản phát hành gần nhất. Trước release, nên chạy lại với artifact chính thức để tránh khác biệt do build profile hoặc bước đóng gói.

Trong multi-module project, mỗi module có public API riêng cần baseline riêng. Nếu module A công khai method nhận kiểu `B`, thay đổi ở B có thể ảnh hưởng API của A dù JAR A không thay đổi. Cần theo dõi dependency giữa các artifact và chạy kiểm tra theo thứ tự phù hợp.

## 9. Những giới hạn và nguồn sai lệch của API diff

API comparison chỉ có ý nghĩa khi đầu vào và phạm vi đúng. Một số tình huống dễ làm báo cáo thiếu hoặc thừa phát hiện:

- So sánh sai artifact, sai classifier hoặc sai version.
- Artifact mới chưa bao gồm generated source/classes, bytecode enhancement hoặc module descriptor giống gói release.
- Scope package/access level giữa hai lần chạy không giống nhau.
- Thiếu dependency khiến công cụ không phân giải được kiểu cha, interface hoặc kiểu tham chiếu.
- Public API bị lọc nhầm hoặc internal API bị đưa vào báo cáo quá rộng.
- Consumer dùng reflection, string-based lookup, service loader hoặc framework convention mà cấu trúc API diff không mô tả đầy đủ.
- Thay đổi hành vi, hiệu năng, bảo mật, network hoặc dữ liệu không thể được kết luận chỉ từ chữ ký API.
- Annotation, generic metadata hoặc module exports có ý nghĩa với framework nhưng bị bỏ qua trong policy hiện tại.

Nếu công cụ báo lỗi phân giải class hoặc thiếu dependency, không nên bỏ qua rồi kết luận API tương thích. Hãy bổ sung classpath/dependency cần thiết hoặc ghi rõ giới hạn của báo cáo. Nếu report quá nhiều khác biệt, hãy kiểm tra filter trước khi thêm hàng loạt ignore.

Một số thay đổi nội bộ có thể xuất hiện trong báo cáo dù không thuộc hợp đồng công khai. Có thể loại chúng bằng filter, nhưng cần giữ filter trong version control và review như một phần của policy API. Không dùng ignore để che các breaking change chưa được đánh giá.

## 10. Ví dụ quy trình review một bản phát hành

Giả sử thư viện `customer-client` đang ở phiên bản `2.3.0` và nhóm chuẩn bị phát hành `2.4.0`.

**Bước 1 — Chọn baseline.** Lấy JAR `customer-client-2.3.0.jar` từ artifact repository và xác minh version/checksum.

**Bước 2 — Build candidate.** Build `customer-client-2.4.0-SNAPSHOT.jar` bằng cùng profile, compiler/toolchain và bước đóng gói dự kiến phát hành.

**Bước 3 — Chạy API diff.** Dùng japicmp hoặc Revapi so sánh hai JAR với scope public/protected API đã thống nhất. Lưu HTML/XML hoặc report có cấu trúc.

**Bước 4 — Phân loại từng phát hiện.** Ví dụ, một method mới là mở rộng; một method bị xóa là breaking candidate; thay đổi internal package có thể nằm ngoài hợp đồng nếu filter đã xác minh đúng.

**Bước 5 — Kiểm tra consumer.** Tìm các ứng dụng đang phụ thuộc `customer-client`, biên dịch consumer cũ với artifact mới và chạy integration test cho các luồng chính.

**Bước 6 — Quyết định release.** Nếu có breaking change không được dự kiến trong minor release, khôi phục API cũ, cung cấp giai đoạn deprecation hoặc chuyển thay đổi sang major release. Nếu breaking change là chủ đích, cập nhật migration guide và yêu cầu consumer có kế hoạch chuyển đổi.

**Bước 7 — Lưu bằng chứng.** Lưu baseline, candidate, tool version, cấu hình filter, report, quyết định review và các ngoại lệ đã duyệt.

## 11. Checklist trước khi chấp nhận API diff

- [ ] Artifact cũ là bản baseline đã phát hành hoặc được phê duyệt.
- [ ] Artifact mới là đúng gói sẽ phát hành.
- [ ] Hai artifact có đúng group/artifact/version/classifier và checksum.
- [ ] Phiên bản japicmp hoặc Revapi và extension được cố định trong build.
- [ ] Phạm vi public/protected API, package và JPMS module được xác định rõ.
- [ ] Dependency cần thiết để phân tích kiểu tham chiếu đã được cung cấp.
- [ ] Report đã được lưu và có thể truy vết tới lần build.
- [ ] Mỗi breaking candidate đã được owner đánh giá.
- [ ] Consumer mẫu đã được biên dịch hoặc kiểm thử với artifact mới khi phù hợp.
- [ ] Behavioral, runtime, security và data compatibility được kiểm thử riêng.
- [ ] Ignore/filter có lý do, phạm vi và người phê duyệt.
- [ ] Versioning và release notes phản ánh đúng mức độ thay đổi.

## 12. Kết luận đánh giá

Japicmp và Revapi giúp tự động hóa việc phát hiện khác biệt trong API Java giữa hai bản phát hành. Japicmp phù hợp khi cần tập trung vào binary API và phân loại thay đổi trực tiếp; Revapi phù hợp khi cần framework có filter, mức độ, ngoại lệ và reporter tùy chỉnh. Cả hai đều cần artifact baseline chính xác, artifact mới đúng quy trình release và phạm vi API được định nghĩa rõ.

Kết quả công cụ là đầu vào cho review, không phải quyết định phát hành tự động trong mọi trường hợp. Nhóm cần kết hợp báo cáo với hợp đồng đã công bố, consumer thực tế, kiểm thử source/binary/behavioral compatibility và chính sách versioning. Khi mỗi thay đổi có bằng chứng, owner và quyết định rõ ràng, API comparison trở thành một bước kiểm soát lặp lại được trong CI và giúp giảm nguy cơ vô tình phá vỡ ứng dụng phụ thuộc.
