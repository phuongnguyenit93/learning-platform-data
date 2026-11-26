# Đọc Reference Guide, API và release notes theo đúng phiên bản

## Bối cảnh và mục tiêu

Bài học thuộc chương **Nền tảng và phiên bản** của module `SPRING_WEB_FLOW`. Module này tìm hiểu cách dùng Spring Web Flow để mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; đồng thời thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng khi có lỗi. Muốn áp dụng các nội dung đó an toàn, trước hết cần đọc tài liệu đúng với phiên bản thư viện thực sự chạy trong ứng dụng.

Spring Web Flow gắn với hệ sinh thái Spring, đặc biệt là Spring MVC và Spring Framework. Cách cấu hình, chữ ký API, dependency được kéo theo và yêu cầu tương thích có thể thay đổi giữa các bản phát hành. Một ví dụ hợp lệ trong Reference Guide của phiên bản khác có thể không biên dịch hoặc có hành vi khác trong dự án hiện tại. Vì vậy, mọi tra cứu kỹ thuật nên bắt đầu bằng việc xác định phiên bản đã được phân giải, sau đó đối chiếu Reference Guide, Javadoc và release notes của chính phiên bản đó.

Sau bài học, bạn có thể:

- Xác định phiên bản Spring Web Flow mà Maven hoặc Gradle thực sự đưa vào classpath.
- Chọn đúng Reference Guide và Javadoc để tra cứu state, event, transition, subflow, binding, validation và scope.
- Dùng release notes để kiểm tra thay đổi, sửa lỗi, yêu cầu tương thích và hướng dẫn nâng cấp.
- Đánh giá một ví dụ hoặc hướng dẫn trên mạng trước khi áp dụng vào ứng dụng Spring MVC.

## 1. Vì sao phải khớp phiên bản tài liệu?

Ba loại tài liệu thường trả lời ba câu hỏi khác nhau:

- **Reference Guide** giải thích mô hình và cách sử dụng: định nghĩa flow, state, transition, subflow, binding dữ liệu, validation, scope, tích hợp Spring MVC và kiểm thử.
- **API documentation (Javadoc)** mô tả hợp đồng lập trình cụ thể: class, interface, constructor, method, tham số, kiểu trả về, ngoại lệ và trạng thái deprecated.
- **Release notes / changelog** ghi lại điều gì thay đổi giữa các bản: tính năng mới, lỗi được sửa, hành vi thay đổi, API bị deprecated hoặc loại bỏ, yêu cầu nền tảng và lưu ý nâng cấp.

Không loại tài liệu nào thay thế hoàn toàn hai loại còn lại. Reference Guide có thể cho biết một transition được khai báo và hoạt động như thế nào, nhưng Javadoc mới là nơi xác nhận method mà mã Java đang gọi có tồn tại với đúng chữ ký hay không. Release notes giúp phát hiện một hành vi đã đổi hoặc một API đã bị đánh dấu deprecated kể từ phiên bản trước.

Ví dụ, khi xây dựng quy trình đăng ký gồm các màn hình nhập thông tin, xác nhận và hoàn tất, nhóm phát triển có thể cần tra cứu cách chuyển từ `ViewState` sang state kế tiếp, cách gửi event khi submit form, cách gọi một subflow và cách giữ dữ liệu trong scope. Hãy kiểm tra các khái niệm đó trong Reference Guide đúng phiên bản; nếu cần gọi API Java, xác nhận tên lớp và chữ ký trong Javadoc tương ứng. Khi nâng cấp thư viện, đọc release notes của toàn bộ các phiên bản nằm giữa bản đang dùng và bản đích.

## 2. Xác định phiên bản thực tế trong dự án

Phiên bản ghi trong một file cấu hình chưa chắc là phiên bản cuối cùng trên runtime classpath. Maven có thể chọn phiên bản thông qua dependency mediation hoặc `dependencyManagement`; Gradle có thể chọn phiên bản theo constraint, platform, resolution rule hoặc dependency khác. Hãy kiểm tra kết quả phân giải của công cụ build.

### Với Maven

Khai báo dependency trực tiếp thường có dạng:

```xml
<dependency>
    <groupId>org.springframework.webflow</groupId>
    <artifactId>spring-webflow</artifactId>
    <version>${spring-webflow.version}</version>
</dependency>
```

Nếu dự án quản lý phiên bản bằng parent POM hoặc BOM, version có thể được kế thừa từ `dependencyManagement`; khi đó hãy kiểm tra nơi quản lý version thay vì thêm một version khác vào dependency.

Chạy các lệnh sau tại thư mục chứa `pom.xml`:

```bash
mvn dependency:tree -Dincludes=org.springframework.webflow:spring-webflow
mvn help:effective-pom
```

`dependency:tree` cho biết dependency được chọn và đường dẫn dependency đưa nó vào. `effective-pom` cho thấy cấu hình sau khi Maven áp dụng parent, profile và dependency management. Nếu dự án có nhiều module, chạy lệnh trong đúng module triển khai ứng dụng.

### Với Gradle

Chạy tại thư mục chứa Gradle build:

```bash
./gradlew dependencyInsight --dependency spring-webflow --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
```

`dependencyInsight` giải thích vì sao một phiên bản được chọn, chẳng hạn do conflict resolution hoặc constraint. `dependencies` hiển thị cây dependency của cấu hình. Với dự án dùng cấu hình runtime riêng, hãy chọn đúng cấu hình mà ứng dụng triển khai thực tế sử dụng.

### Đối chiếu thêm các thành phần liên quan

Ghi lại ít nhất các thông tin sau trước khi mở tài liệu:

| Thành phần | Cần xác định |
| --- | --- |
| Spring Web Flow | Phiên bản đã resolve của `org.springframework.webflow:spring-webflow` |
| Spring Web Flow Test | Nếu có dùng, kiểm tra artifact kiểm thử có cùng dòng phiên bản phù hợp với thư viện chính |
| Spring Framework / Spring MVC | Phiên bản thực tế của các module Spring liên quan |
| Java | Phiên bản JDK dùng để biên dịch và phiên bản runtime triển khai |
| Servlet container và thư viện tích hợp | Phiên bản API/container mà ứng dụng đang chạy cùng |

Spring Web Flow tích hợp với Spring MVC nên không thể kết luận tương thích chỉ từ version của riêng Spring Web Flow. Hãy kiểm tra release notes và thông tin dependency của các thành phần liên quan. Nếu Spring Boot hoặc một BOM đang quản lý phiên bản, cần hiểu cơ chế quản lý đó trước khi override thủ công.

## 3. Chọn đúng Reference Guide

Trên trang tài liệu Spring chính thức, chọn đúng dòng sản phẩm Spring Web Flow và đúng phiên bản đã resolve. Kiểm tra version hiển thị trong tiêu đề, phần tải xuống hoặc đường dẫn tài liệu; không mặc định trang được công cụ tìm kiếm đưa lên đầu là phiên bản dự án cần dùng. Nếu tài liệu của bản cũ không còn được hiển thị trực tiếp, tìm tài liệu lưu trữ hoặc tag tương ứng với bản phát hành đó.

Khi đọc Reference Guide, đi theo câu hỏi của tính năng đang triển khai:

1. **Mô hình flow:** flow được đăng ký và khởi tạo như thế nào; entry point và flow execution được cấu hình ra sao?
2. **State và transition:** state nào biểu diễn một màn hình, một hành động hoặc một nhánh quyết định; event nào kích hoạt transition; điều kiện chuyển trạng thái được khai báo ở đâu?
3. **Subflow:** khi nào tách một hành trình con thành subflow; dữ liệu đầu vào và kết quả trả về được truyền qua ranh giới flow như thế nào?
4. **Form binding và validation:** dữ liệu form được bind vào model nào; validator được gọi ở thời điểm nào; lỗi validation ảnh hưởng đến transition và việc hiển thị lại view ra sao?
5. **Scope và vòng đời:** dữ liệu nên nằm trong request, view, flow hay conversation scope; dữ liệu tồn tại trong bao lâu và khi nào được giải phóng?
6. **Spring MVC và phiên:** flow được ánh xạ vào request như thế nào; flow execution được tiếp tục qua các request ra sao; cấu hình session và xử lý request cần lưu ý điều gì?
7. **Kiểm thử và lỗi:** cách khởi tạo flow trong test, phát event, kiểm tra state tiếp theo, kiểm tra dữ liệu và mô phỏng lỗi hoặc luồng bị gián đoạn.

Đọc phần khái niệm trước khi sao chép cấu hình. Sau đó tìm ví dụ gần với use case, ghi rõ ví dụ thuộc phiên bản nào và xác định những thành phần nào trong ví dụ phụ thuộc vào cấu hình của dự án.

## 4. Dùng Javadoc để xác minh API

Khi Reference Guide nhắc đến một kiểu Java hoặc khi mã nguồn cần gọi trực tiếp API, mở Javadoc cùng phiên bản Spring Web Flow. Tra cứu theo tên lớp hoặc interface, rồi kiểm tra:

- Package đầy đủ và quan hệ giữa interface với implementation.
- Constructor hoặc factory method có sẵn và cách khởi tạo được hỗ trợ.
- Tên method, kiểu tham số, kiểu trả về và checked exception.
- Annotation, generic type hoặc overload có liên quan.
- Ghi chú `Deprecated`, `Since` và liên kết tới API thay thế.

Trong quá trình học Spring Web Flow, có thể gặp các tên như `FlowExecutor`, `FlowDefinitionRegistry`, `RequestContext` hoặc các thành phần mô tả state và transition. Hãy dùng Javadoc của phiên bản đang chạy để xác nhận package, chữ ký và vai trò của từng kiểu; không suy ra rằng một class hoặc method có mặt chỉ vì thấy nó trong một bài viết cũ.

Ví dụ, nếu một action cần đọc dữ liệu từ request context hoặc điều khiển kết quả của một event, hãy tra `RequestContext` và API liên quan trong Javadoc. Sau đó quay lại Reference Guide để hiểu thời điểm action chạy trong flow lifecycle. API cho biết cách gọi; Reference Guide giải thích ngữ cảnh và ý nghĩa của thao tác.

Nếu Javadoc trực tuyến không còn sẵn cho bản đang dùng, có thể kiểm tra tài liệu đi kèm artifact hoặc mã nguồn đúng version. Đảm bảo source JAR hoặc tag mã nguồn khớp với version đã resolve, tránh đọc nhánh phát triển mới nhất rồi áp dụng ngược cho bản cũ.

## 5. Đọc release notes và đánh giá nâng cấp

Khi nâng Spring Web Flow từ phiên bản A lên phiên bản B, hãy lập danh sách tất cả các bản phát hành nằm giữa A và B và đọc ghi chú theo thứ tự tăng dần. Chỉ đọc ghi chú của bản đích có thể bỏ qua một thay đổi quan trọng được giới thiệu ở phiên bản trung gian.

Với mỗi bản phát hành, tìm các mục:

- **Compatibility / prerequisites:** yêu cầu về Java, Spring Framework, Spring MVC, Servlet API hoặc nền tảng liên quan.
- **Breaking changes:** thay đổi có thể khiến cấu hình, flow definition hoặc mã Java cũ không còn hoạt động.
- **Deprecations and removals:** API đã bị cảnh báo hoặc bị loại bỏ; xác định hướng thay thế và thời điểm cần chuyển đổi.
- **Behavior changes:** thay đổi về binding, validation, scope, event, transition, xử lý exception hoặc flow execution.
- **Bug fixes:** lỗi đã được sửa có liên quan đến hành trình nhiều bước, khôi phục flow, session hoặc tích hợp MVC.
- **Known issues:** giới hạn đã biết và cách khắc phục được nhà phát triển công bố.

Phân biệt rõ một tính năng mới với một thay đổi hành vi. Tính năng mới có thể không liên quan đến ứng dụng hiện tại, trong khi một thay đổi mặc định hoặc một bản sửa lỗi có thể tác động đến flow đang chạy dù mã nguồn không đổi.

Với ứng dụng đang có người dùng, hãy biến các ghi chú liên quan thành trường hợp kiểm thử hồi quy. Ví dụ: gửi form không hợp lệ phải hiển thị lại đúng view và giữ dữ liệu phù hợp; gửi event hợp lệ phải đi đúng transition; subflow phải nhận dữ liệu đầu vào và trả kết quả đúng; refresh hoặc back theo cách ứng dụng hỗ trợ không được làm flow rơi vào trạng thái không mong muốn; lỗi ở bước giữa phải được xử lý và cho phép người dùng tiếp tục hoặc bắt đầu lại theo quy tắc sản phẩm.

## 6. Quy trình tra cứu cho một thay đổi cụ thể

Giả sử nhóm cần bổ sung một bước xác nhận vào flow đặt hàng. Hãy thực hiện theo trình tự sau:

1. **Mô tả câu hỏi:** cần thêm một state xác nhận, nhận event submit, kiểm tra dữ liệu và chuyển sang bước hoàn tất.
2. **Chụp lại bối cảnh build:** ghi version Spring Web Flow đã resolve, version Spring Framework/Spring MVC, Java và cơ chế quản lý dependency.
3. **Đọc Reference Guide đúng version:** tìm phần flow definition, view state, transition, binding, validation và scope liên quan.
4. **Xác minh API:** nếu cần viết action hoặc Java flow builder, kiểm tra kiểu và chữ ký trong Javadoc đúng version.
5. **Kiểm tra release notes:** nếu dự án đang nâng cấp, đọc tuần tự các bản phát hành từ version hiện tại đến version đích và đánh dấu mọi thay đổi chạm tới luồng đặt hàng.
6. **Đối chiếu ví dụ:** so sánh ví dụ tài liệu với cấu hình Spring MVC, flow registry và dependency thực tế của dự án; không sao chép nguyên xi một cấu hình thuộc phiên bản khác.
7. **Biến kết quả tra cứu thành kiểm thử:** kiểm tra cả đường đi thành công, validation thất bại, subflow trả lỗi, phiên hết hạn hoặc flow execution không còn hợp lệ theo cách ứng dụng xử lý.
8. **Ghi lại quyết định:** lưu version tài liệu đã đọc, mục tài liệu/Javadoc/release note liên quan và lý do chọn cách triển khai để người khác có thể tái kiểm chứng.

Quy trình này cũng áp dụng khi nghiên cứu scope hoặc session. Ví dụ, trước khi chuyển dữ liệu từ view scope sang flow scope, hãy xác nhận vòng đời của scope trong Reference Guide đúng version và kiểm tra hành vi khi người dùng gửi nhiều request. Sau đó viết test chứng minh dữ liệu còn tồn tại đúng thời điểm và được giải phóng khi flow kết thúc.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách xử lý |
| --- | --- |
| Dùng tài liệu `latest` cho một dự án đang chạy bản cũ | Xác định version đã resolve rồi mở tài liệu lưu trữ đúng bản |
| Chỉ nhìn version khai báo trong `pom.xml` hoặc `build.gradle` | Kiểm tra dependency tree, effective POM hoặc dependency insight |
| Dùng Javadoc của Spring Framework để suy ra API của Spring Web Flow | Tra đúng artifact và đúng Javadoc của Spring Web Flow; kiểm tra riêng các dependency tích hợp |
| Nâng cấp và chỉ đọc release notes của bản đích | Đọc các ghi chú của mọi bản phát hành nằm giữa bản nguồn và bản đích |
| Sao chép một cấu hình XML hoặc ví dụ Java từ blog mà không kiểm tra version | Đối chiếu cấu hình với Reference Guide và API của version dự án |
| Cho rằng dependency biên dịch được thì chắc chắn tương thích runtime | Kiểm tra cả Java, Spring MVC, Servlet container và các dependency đã resolve; chạy kiểm thử tích hợp |
| Thấy API deprecated nhưng không tìm hướng thay thế | Đọc ghi chú deprecated trong Javadoc và release notes, rồi lập kế hoạch chuyển đổi |

## 8. Checklist trước khi áp dụng hướng dẫn

- [ ] Tôi đã xác định version Spring Web Flow thực tế trên runtime classpath.
- [ ] Tôi đã kiểm tra version Spring Framework/Spring MVC, Java và các thành phần tích hợp.
- [ ] Reference Guide tôi đang đọc ghi rõ đúng version cần dùng.
- [ ] Javadoc khớp với artifact Spring Web Flow đã resolve.
- [ ] Tôi đã đọc release notes của các phiên bản trung gian nếu đang nâng cấp.
- [ ] Tôi đã kiểm tra các thay đổi liên quan đến state, event, transition, subflow, binding, validation, scope, session và Spring MVC.
- [ ] Ví dụ được đối chiếu với cấu hình của dự án và có kiểm thử cho cả đường đi thành công lẫn lỗi.
- [ ] Quyết định kỹ thuật có ghi lại version và nguồn tài liệu để nhóm có thể kiểm tra lại.

## 9. Bài tập thực hành

Trong một ứng dụng Spring MVC sử dụng Spring Web Flow, hãy chọn một flow có ít nhất hai view state và một transition. Nếu chưa có dự án mẫu, mô tả một flow giả định gồm nhập thông tin, xác nhận và hoàn tất.

1. Chạy Maven hoặc Gradle để xác định version Spring Web Flow đã resolve. Ghi lại cả version Spring MVC và Java.
2. Mở Reference Guide và Javadoc khớp version. Tìm phần mô tả state, event, transition và form validation.
3. Tìm API được dùng để truy cập request context hoặc đăng ký flow, rồi ghi lại package và chữ ký cần thiết.
4. Chọn một lần nâng cấp giả định hoặc một phiên bản đích do nhóm cung cấp. Đọc release notes theo thứ tự từ bản hiện tại đến bản đích và ghi lại thay đổi có thể ảnh hưởng flow.
5. Đề xuất ít nhất ba kiểm thử hồi quy: submit hợp lệ, submit không hợp lệ và lỗi hoặc gián đoạn khi đi qua một bước của flow.

**Tiêu chí hoàn thành:** người học chỉ ra được version thực tế từ kết quả build; chọn được ba loại tài liệu đúng version; giải thích được vì sao mỗi loại tài liệu được dùng; và liên hệ được một ghi chú phát hành với thay đổi hoặc kiểm thử cụ thể trong flow. Không chấp nhận kết luận chỉ dựa trên tên version khai báo hoặc một ví dụ không rõ nguồn.

## Kết luận

Đọc tài liệu theo đúng phiên bản là một phần của quy trình phát triển Spring Web Flow. Hãy xác định dependency đã resolve, dùng Reference Guide để hiểu mô hình flow, dùng Javadoc để xác minh hợp đồng API và dùng release notes để đánh giá thay đổi theo thời gian. Cách làm này giúp nhóm xây dựng state, event, transition, subflow, form binding và validation phù hợp với môi trường Spring MVC đang triển khai, đồng thời giảm rủi ro khi kiểm thử, xử lý lỗi và nâng cấp thư viện.
