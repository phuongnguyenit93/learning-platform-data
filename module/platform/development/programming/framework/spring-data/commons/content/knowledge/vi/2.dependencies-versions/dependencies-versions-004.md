# Kiểm tra dependency tree và phát hiện lệch phiên bản

## Mục tiêu bài học

Trong ứng dụng Spring Data, việc khai báo một starter hoặc một dependency chưa cho biết đầy đủ những thư viện và phiên bản sẽ được dùng. Spring Data JPA, MongoDB và các module khác có thể đưa Spring Data Commons vào gián tiếp. BOM, dependency management, dependency trực tiếp và quy tắc phân giải xung đột cùng ảnh hưởng đến phiên bản cuối cùng.

Bài học thuộc chương **Phụ thuộc và phiên bản** của module SPRING_DATA_COMMONS. Mục tiêu là đọc được dependency tree, tìm nguyên nhân một phiên bản Commons được chọn và phát hiện những trường hợp bộ thư viện thực tế khác với bộ phiên bản dự kiến.

Sau bài học, bạn có thể:

- Phân biệt phiên bản được yêu cầu, được quản lý, được chọn và thực sự được nạp khi chạy.
- Dùng báo cáo Maven hoặc Gradle để lần theo dependency trực tiếp và bắc cầu.
- Nhận diện override, constraint hoặc quy tắc phân giải làm lệch phiên bản.
- Đề xuất cách sửa dựa trên bộ phiên bản tương thích thay vì chỉnh từng JAR theo cảm tính.
- Kiểm tra đúng module, phạm vi classpath và môi trường có lỗi.

Các lệnh bên dưới là hướng dẫn thực hành cho dự án của người học. Dùng nhóm lệnh phù hợp với công cụ build của dự án; không cần chuyển đổi giữa Maven và Gradle để làm cùng một việc. Ví dụ Windows giả định dự án có wrapper tương ứng.

## 1. Vì sao cần kiểm tra Commons trong dependency tree?

Spring Data Commons cung cấp những hợp đồng và hạ tầng chung như repository, CRUD, phân trang, sắp xếp, xử lý truy vấn, projection, Query by Example, auditing và metadata. Các module lưu trữ sử dụng phần nền tảng đó để tích hợp với công nghệ cụ thể.

Ví dụ, ứng dụng có thể khai báo Spring Data JPA mà không khai báo Commons trực tiếp:

~~~text
Ứng dụng
  -> starter hoặc module Spring Data JPA
       -> Spring Data Commons
       -> các dependency phục vụ JPA
~~~

Một thư viện mở rộng cũng có thể kéo Commons vào qua một đường khác:

~~~text
Ứng dụng
  -> thư viện mở rộng repository
       -> Spring Data Commons
~~~

Khi hai đường đi yêu cầu những phiên bản khác nhau, công cụ build phải quyết định phiên bản nào được sử dụng trên classpath đang xét. Phiên bản được chọn có thể chịu tác động của BOM hoặc một khai báo ghi đè nằm ngoài chỗ khai báo starter.

Hậu quả có thể xuất hiện ngay lúc khởi động repository, lúc tạo projection, hoặc chỉ khi gọi một chức năng auditing hay metadata cụ thể. Việc ứng dụng đã biên dịch được chưa chứng minh mọi thành phần hạ tầng có thể liên kết và hoạt động đúng khi chạy.

Tuy vậy, hai yêu cầu phiên bản khác nhau trong đồ thị chưa tự chứng minh ứng dụng bị lỗi. Cần xem phiên bản được chọn, nguồn quản lý và tính tương thích của các thành phần thực sự dùng nó.

## 2. Bốn lớp thông tin cần phân biệt

| Lớp thông tin | Câu hỏi cần trả lời | Nguồn bằng chứng |
| --- | --- | --- |
| Phiên bản được yêu cầu | Một dependency trực tiếp hoặc bắc cầu đề nghị phiên bản nào? | Khai báo dependency và các đường đi trong đồ thị. |
| Phiên bản được quản lý hoặc bị ràng buộc | BOM, dependency management, constraint hoặc rule quy định điều gì? | Effective POM, cấu hình platform, constraint và quy tắc phân giải. |
| Phiên bản được chọn | Resolver quyết định dùng phiên bản nào cho classpath đang xét? | Dependency tree, báo cáo dependencies và dependency insight. |
| Phiên bản thực sự được nạp | Tiến trình đang chạy lấy class từ JAR hoặc nguồn nào? | Artifact triển khai và thông tin class loading của tiến trình đó. |

Bốn lớp này có thể khác nhau mà không mâu thuẫn. Ví dụ, một thư viện yêu cầu Commons cũ, BOM quản lý Commons ở bản khác, resolver chọn bản do BOM quản lý, còn môi trường triển khai lại đang chạy artifact được đóng gói từ lần build trước.

Vì thế, câu “dự án dùng Commons phiên bản nào?” chỉ có ý nghĩa khi kèm theo ngữ cảnh: module nào, configuration hoặc scope nào, profile nào và bản triển khai nào.

### Phiên bản lệch so với điều gì?

Trong bài này, **lệch phiên bản** là trường hợp phiên bản được chọn hoặc được nạp khác với bộ phiên bản mà dự án dự định sử dụng và kiểm chứng.

Điểm so sánh thường là bộ dependency do Spring Boot quản lý, một Spring Data BOM được dự án chủ động chọn, hoặc một cấu hình phiên bản đã được xác nhận cho dự án.

Không dùng quy tắc “mọi artifact Spring đều phải có cùng số phiên bản”. Spring Boot, Spring Framework, Spring Data Commons và các module Spring Data có hệ phiên bản và vòng đời riêng. Ngay trong hệ Spring Data, tên hoặc số của một release train/BOM cũng không phải yêu cầu mọi artifact mang cùng chuỗi phiên bản.

## 3. Hiểu đường đi của dependency trước khi đọc báo cáo

### 3.1. Dependency trực tiếp và bắc cầu

- **Dependency trực tiếp** được khai báo cho chính module ứng dụng.
- **Dependency bắc cầu** xuất hiện vì một dependency khác cần nó.
- **Dependency management hoặc platform** cung cấp thông tin quản lý hay ràng buộc phiên bản; riêng việc quản lý một dependency chưa đồng nghĩa đưa JAR đó vào classpath.

Ví dụ, một BOM có thể quản lý Commons ngay cả khi ứng dụng chưa sử dụng module Spring Data nào. Muốn có Commons trong đồ thị thực tế, vẫn cần một dependency trực tiếp hoặc bắc cầu dẫn đến nó.

### 3.2. Cùng một artifact xuất hiện nhiều lần trong cây

Đồ thị dependency có thể có nhiều đường đi tới cùng một artifact. Báo cáo dạng cây thường phải biểu diễn lại các đường đi đó bằng ký hiệu rút gọn.

~~~text
Ứng dụng
  +-> module JPA ---------+
  |                      +-> spring-data-commons
  +-> thư viện mở rộng ---+
~~~

Hai đường đi tới Commons không tự động có nghĩa hai bản Commons được đặt vào cùng một classpath. Resolver có thể chọn một phiên bản dùng chung và ghi chú những yêu cầu còn lại là đã bị thay thế hoặc bị lược bỏ.

Cần tách ba hiện tượng:

1. Có nhiều đường đi tới cùng artifact.
2. Có nhiều yêu cầu phiên bản cho artifact đó.
3. Có nhiều bản JAR hoặc nhiều class trùng tên thực sự xuất hiện trong môi trường chạy.

Dependency tree chủ yếu giúp quan sát hai hiện tượng đầu. Hiện tượng thứ ba có thể cần kiểm tra thêm artifact đóng gói, classloader hoặc thư viện do môi trường chạy cung cấp.

## 4. Kiểm tra với Maven

### 4.1. Bắt đầu từ đúng module và cấu hình

Đứng trong module ứng dụng cần phân tích, chạy:

~~~powershell
.\mvnw.cmd dependency:tree
~~~

Đây là báo cáo dependency của dự án theo cấu hình Maven đang có hiệu lực. Nếu dự án có nhiều module, hãy xác định module tạo ra ứng dụng có lỗi. Báo cáo của module thư viện dùng chung chưa chắc phản ánh toàn bộ dependency của ứng dụng cuối.

Nếu lỗi chỉ xuất hiện khi bật một profile, dùng cùng profile đó khi phân tích:

~~~powershell
.\mvnw.cmd -Pproduction dependency:tree
~~~

Tên profile ở đây chỉ là ví dụ và phải được thay bằng profile thực tế. Không tự thêm một profile không tồn tại rồi coi kết quả là đại diện cho môi trường triển khai.

### 4.2. Thu hẹp vào các artifact Spring Data

~~~powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.data:*" -Dverbose
~~~

Để tập trung vào Commons:

~~~powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.springframework.data:spring-data-commons" -Dverbose
~~~

Báo cáo lọc giúp tìm phiên bản và đường đi quan trọng nhanh hơn. Khi cần hiểu đầy đủ dependency bao quanh, quay lại báo cáo không lọc. Không coi phần không xuất hiện trong một báo cáo đã lọc là bằng chứng rằng dependency đó hoàn toàn không tồn tại.

Tùy phiên bản Maven Dependency Plugin và cách hiển thị, phần verbose có thể cung cấp thông tin dependency bị lược bỏ hoặc phiên bản được quản lý. Cách trình bày cụ thể có thể khác, nhưng mục tiêu vẫn là xác định yêu cầu nào bị thay thế và phiên bản nào còn được chọn.

### 4.3. Đọc một tình huống xung đột

Đoạn sau là dữ liệu minh họa đã rút gọn. Các số phiên bản chỉ dùng để giải thích cơ chế phân giải, không phải bộ phiên bản được đề xuất cho dự án.

~~~text
com.example:customer-app:jar:1.0
+- com.example:repository-extension:jar:1.0:compile
|  \- (org.springframework.data:spring-data-commons:jar:3.2.5:compile
|      - omitted for conflict with 3.3.1)
\- org.springframework.data:spring-data-commons:jar:3.3.1:compile
~~~

Cách đọc:

- Ứng dụng phụ thuộc trực tiếp vào thư viện mở rộng.
- Thư viện mở rộng yêu cầu Commons 3.2.5.
- Ứng dụng cũng khai báo trực tiếp Commons 3.3.1.
- Trong tình huống này, resolver chọn 3.3.1; yêu cầu 3.2.5 không tạo thêm một bản Commons tương ứng trên classpath đang xét.

Với Maven, quy tắc hòa giải dependency thông thường ưu tiên đường đi gần dự án hơn; khi các đường đi có cùng độ sâu, thứ tự khai báo có thể ảnh hưởng đến kết quả. Dependency management cũng có thể quản lý phiên bản bắc cầu. Vì vậy, không nên suy luận rằng Maven luôn chọn bản có số lớn nhất.

Dù chỉ còn một phiên bản được chọn, vẫn cần xem thư viện mở rộng có tương thích với Commons đó hay không. Chọn được một phiên bản duy nhất là kết quả phân giải dependency; tương thích nhị phân và hành vi là câu hỏi tiếp theo.

### 4.4. Dùng effective POM để tìm nguồn quản lý

~~~powershell
.\mvnw.cmd help:effective-pom -Dverbose
~~~

Effective POM giúp quan sát cấu hình đã được tổng hợp từ POM hiện tại, parent, profile đang hoạt động và dependency management liên quan. Tùy khả năng của plugin, chế độ verbose có thể bổ sung thông tin nguồn của các phần tử cấu hình.

Khi Commons khác dự kiến, kiểm tra:

- Có khai báo trực tiếp spring-data-commons kèm version hay không.
- Dependency management đang quản lý Commons ở phiên bản nào.
- Có nhiều BOM hoặc parent cùng ảnh hưởng tới bộ Spring hay không.
- Profile đang bật có thay đổi dependency, property hoặc dependency management hay không.
- Có property được dự án dùng để ghi đè phiên bản hay không.

Ví dụ một khai báo trực tiếp có version:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-commons</artifactId>
    <version>3.3.1</version>
</dependency>
~~~

Trong ví dụ này, version nằm ngay trên dependency trực tiếp có thể giữ Commons ở một bản riêng dù dự án đã có quản lý phiên bản ở cấp khác. Nếu dự án muốn theo bộ phiên bản được quản lý, cần đánh giá việc bỏ version ghi đè hoặc bỏ dependency trực tiếp nếu nó vốn đã được kéo vào đúng cách.

Không xóa dependency trực tiếp chỉ vì nó cũng xuất hiện bắc cầu. Nếu mã của module sử dụng trực tiếp API của Commons, dự án có thể chủ động khai báo dependency đó để thể hiện nhu cầu rõ ràng, đồng thời để BOM quản lý version.

### 4.5. Kiểm tra phạm vi liên quan đến lỗi

~~~powershell
.\mvnw.cmd dependency:tree "-Dscope=runtime"
~~~

Lệnh này giúp tập trung vào tập dependency theo phạm vi runtime mà Maven báo cáo. Cần kết hợp cách đóng gói thực tế của ứng dụng, đặc biệt nếu có dependency mang scope provided, dependency chỉ dùng cho test hoặc thư viện do container cung cấp.

Một bài kiểm thử chạy thành công với dependency test bổ sung không chứng minh artifact triển khai có cùng classpath. Tương tự, dependency ở compile time không tự bảo đảm có mặt trong môi trường runtime cuối cùng.

## 5. Kiểm tra với Gradle

### 5.1. Chọn đúng configuration

Với một ứng dụng Java theo cấu hình thông dụng của Gradle:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Trong dự án nhiều module, chỉ định module ứng dụng:

~~~powershell
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
~~~

:app là tên module minh họa. Configuration có thể khác trong dự án Android, multiplatform hoặc khi plugin định nghĩa mô hình riêng; không mặc định mọi dự án đều có cùng tập configuration.

Những configuration thường cần so sánh trong ứng dụng Java gồm:

| Configuration | Khi nào cần xem |
| --- | --- |
| compileClasspath | Xem dependency dùng để biên dịch mã chính. |
| runtimeClasspath | Xem dependency phục vụ chạy mã chính theo mô hình build. |
| testRuntimeClasspath | Xem dependency khi chạy test và so sánh với runtime của ứng dụng. |

Nếu lỗi xuất hiện ở runtime, bắt đầu với runtime của đúng module. Sau đó mới so sánh compile hoặc test khi có dấu hiệu chênh lệch.

### 5.2. Dùng dependency insight để hỏi “vì sao chọn bản này?”

~~~powershell
.\gradlew.bat :app:dependencyInsight --dependency org.springframework.data:spring-data-commons --configuration runtimeClasspath
~~~

Báo cáo dependencies cho bức tranh tổng thể của configuration. Báo cáo dependencyInsight tập trung vào một dependency, các yêu cầu dẫn tới nó và lý do lựa chọn.

Một báo cáo có thể thể hiện những nguyên nhân như phân giải xung đột, constraint, rule hoặc force. Tên và bố cục phần giải thích phụ thuộc phiên bản Gradle và cơ chế quản lý dependency được dự án sử dụng.

Không dừng ở dòng hiển thị Commons. Hãy đọc phần lý do lựa chọn và các đường đi phía dưới để tìm dependency hoặc chính sách đưa phiên bản đó vào.

### 5.3. Hiểu các ký hiệu phổ biến

Ví dụ rút gọn, tiếp tục dùng số phiên bản minh họa:

~~~text
+--- com.example:repository-extension:1.0
|    \--- org.springframework.data:spring-data-commons:3.2.5 -> 3.3.1
\--- org.springframework.data:spring-data-commons:3.3.1
~~~

Dòng 3.2.5 -> 3.3.1 có nghĩa dependency yêu cầu 3.2.5, nhưng configuration này chọn 3.3.1. Nó không nói rằng Gradle sẽ nạp lần lượt cả hai bản.

Những ký hiệu khác thường gặp:

| Ký hiệu | Cách hiểu |
| --- | --- |
| A -> B | Yêu cầu phiên bản A đã được phân giải thành phiên bản B. |
| (*) | Nhánh dependency đã được hiển thị ở nơi khác nên được rút gọn. |
| (c) | Một dependency constraint; bản thân dòng đó không đại diện cho việc thêm một JAR. |

Với cơ chế phân giải mặc định của Gradle, khi nhiều yêu cầu phiên bản xung đột, phiên bản cao hơn thường được chọn. Tuy nhiên, constraint, platform, phiên bản nghiêm ngặt, force và resolution rule có thể làm thay đổi kết quả hoặc khiến phân giải thất bại.

Vì thế, không áp dụng máy móc quy tắc “đường đi gần nhất” của Maven sang Gradle, cũng không kết luận Gradle luôn chọn số lớn nhất bất kể cấu hình.

### 5.4. Lần theo nguồn constraint hoặc override

Khi dependency insight cho kết quả ngoài dự kiến, kiểm tra cấu hình đang có hiệu lực:

- Dependency khai báo trực tiếp kèm version.
- Platform/BOM được thêm qua platform(...) hoặc cơ chế quản lý dependency tương ứng.
- Constraint có strictly(...) hoặc yêu cầu phiên bản khác.
- enforcedPlatform(...), resolutionStrategy.force(...) hoặc rule tùy biến.
- Convention plugin, cấu hình dùng chung hoặc version catalog mà dự án sử dụng.

Version catalog giúp tập trung khai báo tọa độ và phiên bản, nhưng việc khai báo một alias không tự bảo đảm toàn bộ đồ thị Spring được quản lý tương thích. Nó cũng không thay thế việc quan sát kết quả phân giải của configuration cần kiểm tra.

Tương tự, có plugin Spring Boot trong build Gradle chưa đủ để suy ra cách mọi version đang được quản lý. Cần xác định dự án dùng dependency management plugin, BOM qua platform hay một cơ chế khác, rồi đối chiếu bằng báo cáo thực tế.

## 6. Dùng BOM làm mốc, không đoán qua số phiên bản

### 6.1. Ứng dụng có Spring Boot quản lý dependency

Nếu dự án chủ đích dùng bộ dependency do Boot quản lý, đó là mốc để giải thích vì sao một phiên bản Spring Data được chọn. Việc tự nâng riêng Commons có thể làm Commons tách khỏi các module lưu trữ đang sử dụng nó.

Khi kiểm tra, đặt ba câu hỏi:

1. Cơ chế quản lý dependency của Boot đã thực sự được áp dụng chưa?
2. Dependency của ứng dụng có đang ghi đè kết quả quản lý đó không?
3. Có thư viện hoặc rule buộc resolver chọn một bản khác không?

Với Maven, chỉ dùng spring-boot-maven-plugin để đóng gói không đồng nghĩa đã kế thừa dependency management của Boot. Cần phân biệt plugin build với parent hoặc BOM quản lý dependency.

### 6.2. Ứng dụng tự quản lý bộ Spring Data

Dự án không dùng Boot có thể chọn Spring Data BOM để quản lý một bộ module phù hợp. Tuy nhiên, BOM Spring Data không tự cấu hình cơ sở dữ liệu, không tự đăng ký repository và không thay thế việc đảm bảo tương thích với phần còn lại của ứng dụng.

Dù dùng cách quản lý nào, hãy đọc kết quả quản lý thực tế thay vì suy luận rằng:

- Phiên bản Commons phải bằng phiên bản Spring Boot.
- Module JPA, MongoDB và mọi module khác luôn phải mang cùng chuỗi version.
- Chỉ cần chọn Commons mới nhất là mọi thư viện sẽ tương thích.

BOM hoặc bộ phiên bản đã chọn là mốc kỹ thuật; việc chọn mốc nào thuộc quyết định phiên bản của dự án.

## 7. Nhận diện các mẫu lệch phiên bản thường gặp

| Mẫu quan sát | Nguyên nhân có thể có | Cách điều tra |
| --- | --- | --- |
| Commons khác bản do bộ dependency dự kiến quản lý. | Dependency trực tiếp có version, profile hoặc override. | Xem effective POM hoặc dependency insight và tìm nguồn khai báo. |
| Nhiều yêu cầu Commons nhưng chỉ một bản được chọn. | Các thư viện phụ thuộc vào những dòng phiên bản khác nhau. | Kiểm tra các đường đi và khả năng tương thích của thư viện dùng Commons. |
| Một module Spring Data được nâng riêng, các module còn lại giữ nguyên. | Chỉnh dependency cục bộ ngoài cơ chế BOM. | So sánh cả tập Spring Data với bộ phiên bản dự định dùng. |
| Compile thành công nhưng runtime lỗi liên kết method. | Classpath compile và runtime khác nhau hoặc có thành phần không tương thích. | So sánh configuration/scope và xác định JAR thực sự được nạp. |
| Máy phát triển chạy được, CI hoặc production lỗi. | Profile, tham số build, dependency động, artifact triển khai hoặc môi trường khác nhau. | Thu thập báo cáo từ cùng ngữ cảnh gây lỗi và kiểm tra artifact triển khai. |
| Xóa một dependency khai báo trực tiếp nhưng Commons vẫn còn. | Module khác vẫn kéo Commons vào bắc cầu. | Lần theo những đường đi còn lại trong đồ thị. |
| Đã sửa version nhưng tiến trình vẫn báo lỗi cũ. | Đang chạy artifact cũ hoặc còn nguồn class khác trong runtime. | Xác định đúng bản triển khai và vị trí nạp class trước khi tiếp tục đổi version. |

Một dòng bị thay thế trong tree là dấu hiệu để tìm hiểu, không phải chỉ thị phải xóa ngay dependency tạo ra nó. Việc xử lý phải gắn với nguyên nhân và nhu cầu của ứng dụng.

## 8. Liên hệ với lỗi thực tế

### 8.1. Lỗi liên kết không tự chỉ ra dependency gây lệch

Ví dụ, stack trace có thể chứa:

~~~text
java.lang.NoSuchMethodError: ...
~~~

Lỗi này thường cho biết mã đang chạy tham chiếu một method mà định nghĩa class được nạp không cung cấp theo chữ ký cần thiết. Trong hệ Spring Data, sự không tương thích giữa Commons và thành phần sử dụng nó là một khả năng cần kiểm tra.

Cách phân tích hợp lý:

1. Xác định class và chữ ký method trong lỗi.
2. Xác định thành phần gọi method và thành phần cung cấp class bị gọi.
3. Kiểm tra phiên bản được chọn của những thành phần đó trên runtime classpath.
4. Đối chiếu với bộ phiên bản dự kiến.
5. Nếu tree phù hợp nhưng lỗi vẫn còn, kiểm tra nguồn class thực sự trong tiến trình chạy.

Không mặc định Commons là nguyên nhân chỉ vì stack trace có repository. Lỗi có thể đến từ module Spring Data cụ thể, thư viện mở rộng, Spring Framework hoặc thành phần khác.

### 8.2. Một số dấu hiệu cần phân biệt

| Dấu hiệu | Điều cần kiểm tra |
| --- | --- |
| NoSuchMethodError | Method hoặc chữ ký mà mã gọi cần có có tồn tại trong class được nạp không; các thành phần có tương thích nhị phân không. |
| AbstractMethodError | Hợp đồng và implementation được nạp có khớp nhau không. |
| ClassNotFoundException | Class có mặt và có thể được tìm thấy bởi classloader đang dùng không. |
| NoClassDefFoundError | Class bị thiếu, dependency của nó bị thiếu, hoặc quá trình khởi tạo class đã thất bại trước đó. |
| Không tạo được bean repository | Có thể do cấu hình, mapping, tên truy vấn hoặc dependency; cần đọc nguyên nhân gốc. |

Không coi mọi lỗi khởi động đều là lệch phiên bản. Ví dụ, một derived query dùng sai tên thuộc tính có thể làm repository không khởi tạo được dù bộ dependency hoàn toàn phù hợp.

### 8.3. Khi cần xác định nguồn class được nạp

Trong một tình huống chẩn đoán cụ thể, có thể quan sát nguồn class của Commons từ chính tiến trình có lỗi:

~~~java
import java.security.CodeSource;
import org.springframework.data.repository.Repository;

Class<?> type = Repository.class;
CodeSource source = type.getProtectionDomain().getCodeSource();

System.out.println("class=" + type.getName());
System.out.println(
    "origin=" + (source == null ? "unknown" : source.getLocation())
);
System.out.println(
    "version=" + type.getPackage().getImplementationVersion()
);
~~~

Đây là đoạn lệnh chẩn đoán để đặt trong ngữ cảnh Java phù hợp, không phải một lớp ứng dụng hoàn chỉnh. Giá trị version có thể là null nếu manifest không cung cấp thông tin; vị trí nguồn cũng phụ thuộc cách đóng gói và classloader.

Kết quả chỉ cho biết nguồn của class đang kiểm tra. Nếu lỗi nằm ở một class khác, cần xác định nguồn của chính class đó; một class đúng nguồn chưa chứng minh mọi class trong tiến trình đều đến từ bộ JAR mong đợi.

## 9. Quy trình sửa theo bằng chứng

### Bước 1: Chốt ngữ cảnh tái hiện

Ghi nhận module ứng dụng, profile hoặc tham số build, configuration/scope và môi trường có lỗi. Lấy báo cáo trong chính ngữ cảnh đó.

### Bước 2: Chốt bộ phiên bản dự kiến

Xác định dự án theo quản lý dependency của Boot, Spring Data BOM hay bộ phiên bản được quản lý riêng. Nếu chưa có mốc này, chưa đủ cơ sở kết luận một phiên bản thấp hơn hoặc cao hơn là “sai”.

### Bước 3: Tìm phiên bản được chọn và các nguồn yêu cầu

Tìm Commons trước, sau đó các module lưu trữ và thư viện mở rộng đang sử dụng nó. Đọc cả đường đi và lý do chọn phiên bản.

### Bước 4: Tìm điểm làm kết quả khác dự kiến

Điểm đó có thể là version trực tiếp, dependency management của profile, một platform khác hoặc resolution rule. Sửa đúng nguồn điều khiển thay vì thêm một override thứ hai để chống lại override thứ nhất.

### Bước 5: Chọn thay đổi nhỏ nhưng có ý nghĩa

Một số hướng xử lý tùy nguyên nhân:

- Bỏ version ghi đè không cần thiết để quay về bộ dependency được quản lý.
- Nâng hoặc thay thư viện mở rộng để phù hợp với bộ Spring Data đang dùng.
- Điều chỉnh bộ phiên bản quản lý chung nếu dự án chủ động chuyển dòng Spring Data.
- Thu hẹp hoặc loại bỏ rule đang ép sai phiên bản.

Exclusion chỉ loại bỏ một đường dependency theo cấu hình áp dụng; nó không tự cung cấp một bản thay thế tương thích và có thể không loại bỏ các đường đi khác. Không loại Commons khỏi một module cần nó chỉ để làm báo cáo “hết xung đột”.

Tương tự, force có thể làm resolver chọn một version nhưng không chứng minh version đó cung cấp đầy đủ API mà mọi thư viện cần.

### Bước 6: Xác nhận sau thay đổi

Tạo lại báo cáo với cùng module, profile và classpath; so sánh phiên bản được chọn và nguồn quản lý với dự kiến. Sau đó kiểm tra hành vi có liên quan, chẳng hạn tạo repository, gọi truy vấn có phân trang hoặc luồng auditing từng gây lỗi.

Nếu vấn đề xảy ra ở triển khai, xác nhận artifact đã sửa thực sự được đưa vào môi trường đó. Không thay đổi thêm phiên bản chỉ vì một tiến trình cũ vẫn đang chạy.

## 10. Bài tập đọc báo cáo

Một ứng dụng dự kiến dùng một bộ Spring Data đã được dự án xác nhận. Thư viện repository-extension yêu cầu Commons 3.2.5, nhưng báo cáo của ứng dụng cho thấy 3.3.1 được chọn.

Tiếp tục coi đây là số phiên bản minh họa, hãy trả lời:

1. Có chắc hai bản Commons cùng được đưa vào runtime không?
2. Có thể kết luận 3.3.1 tương thích chỉ vì build thành công không?
3. Nếu 3.3.1 khác bộ dự kiến, cần tìm ở đâu?
4. Nếu tree đúng dự kiến nhưng production vẫn báo lỗi liên kết method, bước tiếp theo là gì?

Gợi ý phân tích:

| Câu hỏi | Kết luận có căn cứ |
| --- | --- |
| Hai phiên bản có cùng ở runtime không? | Chưa thể kết luận từ hai yêu cầu; cần đọc bản được chọn và kiểm tra runtime thực tế nếu cần. |
| Build thành công có đủ không? | Chưa đủ; thư viện mở rộng có thể gọi một API không tương thích khi nhánh chức năng được thực thi. |
| Tìm nguồn chọn bản ngoài dự kiến ở đâu? | Maven: dependency trực tiếp, effective POM và profile; Gradle: dependency insight, platform, constraint và rule. |
| Tree đúng nhưng production còn lỗi thì làm gì? | Kiểm tra đúng artifact triển khai, classpath của tiến trình và nguồn nạp class liên quan tới lỗi. |

Một bản ghi điều tra hữu ích nên có đủ: dependency đang xét, phiên bản được yêu cầu, phiên bản được chọn, nguồn quản lý, ngữ cảnh classpath và hành động sửa. Khi có những bằng chứng này, việc phát hiện lệch phiên bản trở thành một quy trình có thể kiểm chứng thay vì thử thay số version liên tục.