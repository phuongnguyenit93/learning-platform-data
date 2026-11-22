# Chiến lược loại bỏ automatic module trong dự án lâu dài

Automatic module là cầu nối giúp thư viện Java cũ tham gia module path mà chưa cần có module descriptor tường minh. Cơ chế này hỗ trợ chuyển đổi từng bước, nhưng nó không tạo ra ranh giới API và dependency rõ ràng như explicit named module. Nếu dự án muốn tận dụng JPMS lâu dài, mục tiêu nên là mọi dependency được resolve trong runtime module graph đều có module descriptor tường minh, hoặc được thay thế bằng dependency đã có descriptor.

Việc chuyển đổi cần thực hiện theo đồ thị dependency thực tế, bao gồm cả dependency bắc cầu. Chỉ nâng cấp một vài thư viện trực tiếp hoặc thêm thuộc tính Automatic-Module-Name chưa đủ để loại bỏ automatic module.

## 1. Xác định trạng thái đích

Trước khi thay đổi dependency, hãy thống nhất tiêu chí hoàn thành:

- Mỗi module ứng dụng do dự án sở hữu có explicit module descriptor.
- Các thư viện nằm trong resolved runtime module graph đều là explicit named module hoặc system module của JDK.
- Không còn automatic module trong cấu hình chạy production.
- Các dependency legacy đã được nâng cấp, thay thế hoặc chuyển thành explicit modular artifact có descriptor được quản lý và kiểm tra.
- Package API, reflection access và service provider được khai báo có chủ đích.
- Build và CI phát hiện lại automatic module khi một dependency mới được thêm vào.

Không nên đánh đồng mục tiêu này với việc chỉ loại bỏ một dòng cảnh báo. Automatic module có thể vẫn xuất hiện ở dependency bắc cầu dù file build của ứng dụng không khai báo trực tiếp thư viện đó.

Cũng cần phân biệt ba trạng thái:

| Trạng thái | Ý nghĩa | Có đạt mục tiêu loại bỏ automatic module? |
|---|---|---|
| Explicit named module | JAR có module descriptor tường minh, thường là module-info.class | Có |
| Automatic module | JAR không có descriptor nhưng được đặt trên module path; descriptor được suy ra tự động | Không |
| Unnamed module | Code/JAR nằm trên classpath và thuộc unnamed module của class loader | Không phải automatic module, nhưng cũng chưa được modular hóa tường minh |

Đưa một JAR từ module path về classpath chỉ đổi cách nó được nạp sang unnamed module. Đó không phải chuyển đổi thành explicit module và không phải đích cuối của một ứng dụng JPMS hoàn chỉnh.

## 2. Kiểm kê toàn bộ dependency graph

Bắt đầu bằng việc lập danh sách dependency trực tiếp và bắc cầu cho từng module ứng dụng. Phân tích cả compile classpath và runtime classpath vì một thư viện có thể chỉ xuất hiện khi chạy.

Với Gradle, có thể xem dependency tree của cấu hình runtime:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Để hiểu vì sao một artifact cụ thể được kéo vào:

~~~bash
./gradlew :app:dependencyInsight --dependency legacy-codec --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
~~~

Sau khi có danh sách artifact, phân loại từng JAR bằng:

~~~bash
jar --describe-module --file path/to/library.jar
~~~

Kết quả giúp nhận biết JAR có descriptor explicit, automatic module hay chưa phải module trên module path. Với JAR automatic, output của công cụ thường cho biết tên module được suy ra và trạng thái automatic.

Có thể dùng jdeps để phân tích dependency của bytecode và xác định các module cần thiết:

~~~bash
jdeps --print-module-deps --module-path libs path/to/application.jar
~~~

Khi phân tích một ứng dụng multi-release JAR hoặc target JDK cụ thể, cần dùng tùy chọn multi-release tương ứng để kết quả phản ánh đúng bytecode được chạy. Kết quả của jdeps là dữ liệu hỗ trợ điều tra; nó không thay thế việc đọc API, service descriptor và cấu hình reflection của thư viện.

Tạo bảng kiểm kê với các thông tin tối thiểu:

| Trường | Nội dung cần ghi |
|---|---|
| Artifact | group/artifact/version hoặc tọa độ tương ứng |
| Dependency path | Module nào kéo artifact vào, trực tiếp hay bắc cầu |
| Runtime scope | Có xuất hiện trong runtimeClasspath hay không |
| Module status | Explicit, automatic, unnamed/classpath hoặc system module |
| Module name | Tên lấy từ module descriptor hoặc automatic module name |
| Upstream status | Phiên bản mới đã có module-info.class chưa |
| Migration action | Upgrade, replace, contribute descriptor, repackage hoặc giữ ngoại lệ có thời hạn |
| Owner | Người hoặc nhóm chịu trách nhiệm cập nhật và duy trì |

Đừng chỉ ghi tên automatic module. Cần biết dependency nào kéo nó vào để xử lý đúng nguồn trong build graph.

## 3. Ưu tiên nâng cấp lên phiên bản explicit module từ upstream

Đây thường là phương án có chi phí duy trì thấp nhất.

Với mỗi automatic module, kiểm tra release notes và nội dung JAR của các phiên bản mới hơn. Một thư viện có thể đã cung cấp module descriptor trong phiên bản mới, hoặc có một bản phát hành riêng cho Java 9 trở lên.

Quy trình:

1. Xác định dependency trực tiếp hoặc bắc cầu tạo ra automatic module.
2. Tìm phiên bản tương thích đã có module-info.class.
3. Đọc descriptor của phiên bản mới bằng jar --describe-module.
4. Kiểm tra tên module, requires, exports, opens, uses và provides.
5. Nâng cấp dependency trong build file hoặc constraint/version catalog.
6. Chạy compile, unit test, integration test và kiểm tra khởi chạy trên module path.
7. Xác nhận dependency graph runtime không còn automatic module tương ứng.

Không nên giả định tên module của phiên bản mới sẽ giống tên automatic module cũ. Nếu upstream thay đổi module name, các module phụ thuộc phải cập nhật directive requires và có thể cần điều chỉnh cấu hình launcher.

Ưu tiên module name ổn định được upstream công bố. Không tự suy ra tên mới từ tên JAR nếu upstream đã khai báo descriptor chính thức.

## 4. Nếu upstream chưa cung cấp module descriptor

Có ba hướng chính khi thư viện chưa có explicit module.

### 4.1. Đóng góp module descriptor cho upstream

Nếu dự án có thể làm việc với nhà cung cấp hoặc cộng đồng thư viện, hãy đề xuất upstream thêm module-info.java và phát hành phiên bản mới.

Descriptor cần được thiết kế dựa trên API thật:

- Khai báo các dependency trực tiếp bằng requires.
- Chỉ export package mà consumer cần dùng.
- Dùng qualified exports cho SPI nội bộ có consumer xác định.
- Chỉ khai báo opens cho package framework cần deep reflection.
- Khai báo uses và provides cho service nếu thư viện tiêu thụ hoặc cung cấp service.
- Tránh requires transitive nếu dependency không thực sự là một phần API mà consumer cần đọc.

Một descriptor tốt là hợp đồng module của thư viện. Việc thêm descriptor không nên chỉ nhằm làm cho công cụ báo hết automatic module trong khi vẫn export mọi package và khai báo dependency thiếu chính xác.

### 4.2. Tạo explicit modular artifact được dự án quản lý

Nếu source có sẵn hoặc giấy phép cho phép chỉnh sửa/đóng gói lại, dự án có thể tạo một bản modular hóa có kiểm soát:

1. Lấy đúng source hoặc binary artifact và cố định checksum/version nguồn.
2. Dùng jdeps để phân tích dependency và có thể tạo một module-info.java gợi ý.
3. Review thủ công tên module, requires, exports, opens, uses và provides.
4. Biên dịch descriptor với module path/dependency phù hợp.
5. Đóng gói descriptor cùng nội dung thư viện thành một modular JAR mới.
6. Lưu quy trình, source, checksum, patch và kiểm thử trong repository hoặc artifact repository nội bộ.
7. Công bố artifact nội bộ với tọa độ và version riêng, không giả mạo nguồn phát hành upstream.
8. Chạy kiểm thử tương thích và kiểm tra module resolution.

Có thể khởi đầu phân tích bằng:

~~~bash
jdeps --generate-module-info generated-module-info path/to/legacy.jar
~~~

Module descriptor được jdeps sinh ra chỉ là bản gợi ý. Công cụ phân tích bytecode không thể tự quyết định package nào là API được hỗ trợ, package nào cần mở cho reflection, hoặc dependency nào là hợp đồng công khai. Người duy trì phải review descriptor trước khi phát hành.

Không nên sửa trực tiếp JAR vendor đang được build cache hoặc tải từ repository. Hãy tạo artifact đầu ra mới, tái lập được từ một nguồn đầu vào đã cố định. Nếu JAR có chữ ký số, việc thay đổi nội dung làm chữ ký cũ không còn hợp lệ; quy trình phát hành artifact mới phải xử lý chữ ký và provenance theo chính sách của dự án.

### 4.3. Thay thế thư viện khi chi phí modular hóa quá cao

Nếu thư viện không còn được duy trì, có package split, dependency cycle khó xử lý hoặc yêu cầu reflection quá rộng, hãy đánh giá thư viện thay thế có explicit module tốt hơn.

So sánh trên các tiêu chí:

- Tính năng và API cần thiết.
- Tương thích phiên bản Java và dependency khác.
- Hiệu năng và hành vi runtime.
- Service provider và cơ chế reflection.
- Mức độ hoạt động của upstream.
- Khả năng bảo trì lâu dài và giấy phép.
- Khả năng chuyển đổi dữ liệu hoặc API ở lớp adapter.

Đôi khi viết một adapter nhỏ quanh API thay thế có chi phí thấp hơn việc duy trì một fork modular hóa lâu dài.

## 5. Dùng Automatic-Module-Name đúng vai trò trong giai đoạn chuyển tiếp

Thuộc tính manifest **Automatic-Module-Name** cho phép thư viện công bố tên automatic module ổn định khi JAR được đặt trên module path:

~~~text
Automatic-Module-Name: com.acme.legacy.codec
~~~

Điều này giúp consumer không bị phụ thuộc vào tên module suy ra từ tên file JAR. Khi file được đổi tên hoặc version suffix thay đổi, module name vẫn ổn định.

Tuy nhiên, thuộc tính này **không tạo explicit module descriptor**. JAR vẫn là automatic module: package được export rộng, descriptor không thể hiện đầy đủ ranh giới API và dependency theo ý định của tác giả.

Vì vậy:

- Dùng Automatic-Module-Name như biện pháp ổn định tên trong giai đoạn chuyển tiếp.
- Ghi rõ dependency đó vẫn là automatic module trong danh sách migration.
- Không đánh dấu hoàn thành chỉ vì module name đã ổn định.
- Đặt owner và thời hạn xem xét để nâng cấp, đóng góp descriptor hoặc thay thế.

Nếu dự án sở hữu thư viện, có thể phát hành bản tương thích với Automatic-Module-Name trước, sau đó phát hành bản explicit module có cùng tên khi đã thiết kế descriptor. Hãy kiểm tra quy tắc versioning và khả năng tương thích của upstream trước khi chuyển đổi.

## 6. Xử lý package, dependency cycle và service khi chuyển sang explicit module

Khi thêm descriptor, một số vấn đề trước đây bị classpath che khuất sẽ xuất hiện rõ hơn.

### 6.1. Split package

Hai module cùng chứa class thuộc một package có thể gây lỗi khi resolve module graph hoặc làm thiết kế package không rõ quyền sở hữu. Kiểm tra các package bị trùng giữa các JAR trước khi modular hóa.

Cách xử lý thường là:

- Chọn một module sở hữu package.
- Nâng cấp thư viện để package được tổ chức lại.
- Thay thế hoặc tách dependency.
- Di chuyển code nội bộ sang package riêng nếu dự án kiểm soát source.

Không cố xử lý split package bằng cách export thêm package hoặc đưa các JAR vào cùng một module path mà chưa hiểu xung đột.

### 6.2. Dependency cycle

Named module không được tạo chu trình requires. Nếu A requires B và B requires A, cần xem lại ranh giới module.

Các hướng xử lý:

- Tách interface/SPI dùng chung sang module thứ ba.
- Đảo chiều dependency qua abstraction.
- Chuyển phần code dùng chung vào module API độc lập.
- Gộp các phần thực sự không thể tách nếu chúng có cùng vòng đời và trách nhiệm.

Không dùng requires transitive để che giấu một chu trình dependency.

### 6.3. Reflection và framework

Một thư viện có thể hoạt động trên classpath vì classpath không áp dụng strong encapsulation giống named module. Sau khi chuyển sang explicit module, framework có thể cần quyền deep reflection.

Hãy xác định chính xác package và module framework cần truy cập, rồi dùng opens có giới hạn:

~~~java
module com.acme.domain {
    opens com.acme.domain.model to com.acme.orm;
}
~~~

Các tùy chọn --add-opens có thể hữu ích để chẩn đoán hoặc duy trì tương thích tạm thời. Không để các tùy chọn launcher rộng trở thành thiết kế cuối cùng nếu có thể khai báo quyền cụ thể trong descriptor.

### 6.4. ServiceLoader

Kiểm tra cả file cấu hình service cũ trong META-INF/services và descriptor mới. Explicit named module nên khai báo service tiêu thụ bằng uses và provider bằng provides ... with ....

~~~java
module com.acme.application {
    requires com.acme.report.spi;
    uses com.acme.report.spi.ReportExporter;
}
~~~

~~~java
module com.acme.csv.exporter {
    requires com.acme.report.spi;
    provides com.acme.report.spi.ReportExporter
        with com.acme.csv.CsvReportExporter;
}
~~~

Đảm bảo provider module được resolve vào layer mà ứng dụng tìm kiếm. Khi đổi từ automatic sang explicit module, hãy kiểm tra hành vi provider bằng integration test thay vì giả định file META-INF/services cũ sẽ được xử lý giống hệt mọi cấu hình trước đó.

## 7. Tránh dùng classpath để che automatic module

Đưa một JAR từ module path sang classpath làm cho nó thuộc unnamed module. Điều này có thể hữu ích trong một giai đoạn chuyển tiếp khi phần code legacy vẫn chạy trên classpath, nhưng không biến JAR thành explicit named module.

Điểm quan trọng là named module không thể khai báo requires tới unnamed module. Vì thế, nếu một module ứng dụng đã chuyển sang explicit named module cần gọi trực tiếp API của thư viện legacy, việc chuyển thư viện đó về classpath sẽ không giải quyết dependency theo cách thông thường.

Nếu buộc phải giữ thư viện trên classpath trong thời gian ngắn:

- Giữ phần tích hợp legacy ở một ranh giới classpath/unnamed module có kiểm soát.
- Để code ở ranh giới đó gọi các API của named module nếu cần.
- Không để named module phụ thuộc ngược vào classpath code.
- Ghi nhận đây là ngoại lệ migration, có owner và tiêu chí loại bỏ.
- Không tính trạng thái này là hoàn tất modularization của dependency.

Với một ứng dụng muốn có module graph đầy đủ, phương án bền vững vẫn là nâng cấp, thay thế hoặc tạo explicit modular artifact được quản lý.

## 8. Lộ trình migration theo giai đoạn

Có thể chia công việc thành các giai đoạn nhỏ để giữ build chạy được sau mỗi thay đổi.

| Giai đoạn | Việc thực hiện | Điều kiện chuyển bước |
|---|---|---|
| 1. Baseline | Ghi nhận JDK, build tool, module path, classpath và dependency graph hiện tại | Có danh sách dependency runtime trực tiếp và bắc cầu |
| 2. Inventory | Phân loại explicit, automatic, unnamed và system modules; xác định owner | Mọi automatic module có nguồn dependency và phương án xử lý |
| 3. Upstream first | Nâng cấp các dependency đã có explicit module descriptor | Compile/test pass, module name và API được xác nhận |
| 4. Internal modules | Thêm descriptor cho module do dự án sở hữu, thiết kế exports/opens/services | Các module nội bộ resolve được và không có cycle/split package |
| 5. Legacy conversion | Đóng góp descriptor, tạo modular artifact nội bộ hoặc thay thế thư viện còn lại | Mỗi artifact có provenance, version và test |
| 6. Runtime verification | Kiểm tra module resolution trên đúng runtime image/cấu hình production | Không còn automatic module trong resolved runtime graph |
| 7. CI enforcement | Thêm kiểm tra tự động và báo lỗi khi automatic module mới xuất hiện | Dependency mới không thể âm thầm đưa automatic module vào production |

Nên xử lý các thư viện được nhiều module cùng dùng trước, vì một lần nâng cấp hoặc modular hóa có thể loại bỏ automatic module khỏi nhiều dependency path. Với thư viện chỉ xuất hiện trong một nhánh ít dùng, có thể xử lý sau nhưng vẫn cần owner và mốc thời gian.

Sau mỗi thay đổi dependency, chạy test ở đúng JDK mục tiêu. Một thư viện có thể biên dịch thành công nhưng gặp lỗi reflection, service discovery hoặc class loading khi chạy.

## 9. Thiết lập cổng kiểm tra trong CI

Sau khi migration đạt trạng thái ổn định, CI cần ngăn automatic module quay trở lại.

Một quy trình kiểm tra phù hợp:

1. Resolve runtime dependency graph bằng build tool.
2. Thu thập tất cả JAR/module thực sự có mặt trên module path.
3. Dùng jar --describe-module hoặc API ModuleFinder để xác định descriptor từng artifact.
4. Phân loại automatic module và explicit module.
5. So sánh với allowlist ngoại lệ migration có owner, lý do và ngày hết hạn.
6. Làm build thất bại nếu automatic module mới xuất hiện hoặc ngoại lệ đã hết hạn.
7. Chạy ứng dụng với --show-module-resolution trong integration test để xác nhận cấu hình runtime.

Ví dụ lệnh quan sát cấu hình khởi chạy:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.application/com.acme.application.Main
~~~

Không nên chỉ scan file JAR trong thư mục libs nếu build tool resolve dependency từ nhiều nơi hoặc tạo module path động. Cổng CI phải kiểm tra đúng tập artifact của cấu hình runtime thực tế.

Có thể lưu báo cáo migration dạng machine-readable gồm artifact, module name, trạng thái descriptor, dependency path và ngoại lệ được duyệt. Báo cáo phải được sinh lại từ dependency graph của build, không duy trì bằng cách sửa tay sau mỗi lần nâng cấp.

## 10. Tiêu chí nghiệm thu cho từng dependency

Một dependency chỉ được đánh dấu đã loại bỏ automatic module khi:

- Artifact đầu ra có explicit module-info.class.
- Tên module ổn định và được ghi nhận.
- Descriptor có requires đúng với dependency thực tế.
- Exports chỉ công bố package API cần thiết.
- Opens chỉ cấp deep reflection cho package/consumer cần thiết.
- uses/provides được khai báo và service discovery hoạt động nếu thư viện có service.
- Không phát sinh split package hoặc requires cycle trong module graph.
- Compile, unit test, integration test và runtime verification đều đạt.
- Artifact nguồn, checksum, version và quy trình build có thể tái lập.
- Dependency runtime graph không còn automatic module tương ứng.

Nếu một dependency chưa đạt, giữ nó trong danh sách migration với trạng thái và lý do rõ ràng. Không đổi nhãn sang explicit module chỉ vì đã có Automatic-Module-Name.

## 11. Ví dụ về báo cáo migration

Giả sử runtime graph ban đầu có ba automatic module:

| Dependency | Trạng thái ban đầu | Hướng xử lý | Trạng thái đích |
|---|---|---|---|
| legacy-json | Automatic | Nâng cấp lên bản upstream có module-info.class | Explicit |
| old-logging-adapter | Automatic, dependency bắc cầu | Thay bằng adapter đang được duy trì | Explicit |
| vendor-codec | Automatic, chưa có bản modular | Tạo artifact nội bộ có descriptor đã review hoặc thay thế | Explicit |

Sau khi thay đổi, cần chạy lại dependencyInsight/dependency:tree để xác nhận artifact cũ không còn được kéo vào bởi nhánh khác. Tiếp đó, xác nhận module name và descriptor của artifact mới, rồi kiểm tra runtime resolution.

Ví dụ báo cáo cuối của migration có thể ghi:

- Tổng số automatic module trong runtime graph trước migration.
- Số module đã nâng cấp từ upstream.
- Số module đã thay thế.
- Số modular artifact nội bộ đã tạo.
- Số ngoại lệ còn lại, owner và hạn xử lý.
- Kết quả CI gate và integration test trên JDK mục tiêu.

Báo cáo này giúp nhóm biết còn bao nhiêu dependency thực sự cần xử lý, thay vì dựa vào cảm giác rằng ứng dụng đã chuyển sang JPMS vì các module chính đã có module-info.java.

## 12. Nguyên tắc duy trì lâu dài

- Xem Automatic-Module-Name là biện pháp ổn định tên trong migration, không phải explicit module descriptor.
- Theo dõi dependency bắc cầu, không chỉ dependency trực tiếp.
- Ưu tiên descriptor do upstream duy trì; chỉ tạo artifact modular nội bộ khi có quy trình tái lập và owner rõ ràng.
- Không dùng classpath để che một automatic module rồi tuyên bố đã hoàn thành modularization.
- Không export tất cả package hoặc mở toàn module chỉ để làm framework chạy; xác định API và reflection access cần thiết.
- Không dùng requires transitive tùy tiện; chỉ công bố dependency khi consumer thực sự cần đọc nó qua API.
- Kiểm tra service provider, split package, dependency cycle và reflection sau mỗi lần chuyển đổi.
- Đưa kiểm tra automatic module vào CI để dependency mới không làm lùi trạng thái.
- Định kỳ xem xét ngoại lệ và xóa chúng khi upstream hoặc phương án thay thế đã sẵn sàng.

Chiến lược bền vững là quản lý module descriptor như một phần hợp đồng của từng thư viện, đồng thời quản lý dependency graph như một phần của build. Khi mọi dependency runtime đều có descriptor explicit, package API được giới hạn rõ ràng và CI bảo vệ trạng thái đó, dự án có thể tận dụng JPMS mà không phụ thuộc lâu dài vào quy tắc rộng của automatic module.