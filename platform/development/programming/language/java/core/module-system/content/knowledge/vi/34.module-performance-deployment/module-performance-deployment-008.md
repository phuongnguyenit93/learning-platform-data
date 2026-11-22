# Không tối ưu bằng cách loại bỏ boundary cần thiết

## Mục tiêu

Sau bài này, bạn có thể đánh giá chi phí thực tế của module boundary trong JPMS, phân biệt chi phí khởi động với chi phí xử lý request, giải thích vì sao `exports`, `opens` và dependency rõ ràng thường không phải lý do để gộp module, lựa chọn mức phân chia module hợp lý và tối ưu đóng gói/runtime mà vẫn giữ encapsulation cần thiết.

## 1. Module boundary bảo vệ điều gì?

Một named module xác định một đơn vị phụ thuộc và một ranh giới truy cập. Module descriptor cho biết module cần đọc module nào (`requires`), package nào được đưa ra ngoài (`exports`), package nào được mở cho deep reflection (`opens`) và service nào được sử dụng hoặc cung cấp (`uses`, `provides`).

Ví dụ:

~~~java
module com.acme.orders {
    requires com.acme.money;
    exports com.acme.orders.api;
    opens com.acme.orders.persistence to org.example.orm;
}
~~~

Thiết kế này thể hiện ba quyết định khác nhau:

- Module orders phụ thuộc vào module money.
- Consumer có thể sử dụng public API trong package `com.acme.orders.api`.
- ORM được phép deep-reflect vào package persistence.

Các package implementation khác vẫn được giữ bên trong module. Consumer không thể tự ý phụ thuộc vào mọi class public trong module chỉ vì chúng có modifier `public`.

Boundary giúp module kiểm soát hợp đồng mà nó cung cấp. Nếu xóa boundary chỉ vì muốn "nhanh hơn", ứng dụng có thể mất khả năng thay đổi implementation, tăng coupling giữa các thành phần và làm cho việc nâng cấp hoặc kiểm thử khó hơn.

## 2. Không nhầm module boundary với một lần gọi hàm qua mạng

JPMS module là đơn vị tổ chức, phân giải dependency và kiểm soát truy cập trong cùng một JVM. Nó không phải process boundary, network boundary hay cơ chế tự động chuyển lời gọi method qua một lớp proxy.

Một lời gọi Java thông thường:

~~~java
Order order = orderService.findById(orderId);
~~~

vẫn là lời gọi method trong cùng JVM. Nếu consumer đã có reference tới object và method được phép truy cập, việc module chứa class ở một module riêng không biến lời gọi thành RPC hay thêm một network hop.

Cần phân biệt:

- **Module resolution** xảy ra khi JVM khởi động hoặc khi ứng dụng tạo module layer mới. Đây là công việc phân giải graph và metadata.
- **Access/linkage checks** được áp dụng khi class được liên kết và khi JVM cần xác định quyền truy cập tới type/member.
- **Method execution** là phần xử lý nghiệp vụ thực tế sau khi lời gọi đã được thiết lập.
- **Reflection/service loading** có chi phí riêng do cơ chế khám phá hoặc truy cập động; chi phí này không đồng nghĩa với mọi lời gọi method giữa hai module.

Vì vậy, không nên giả định mỗi method call qua module boundary đều có một khoản overhead đáng kể. JPMS không tạo ra một proxy hoặc dispatcher bắt buộc cho mọi lời gọi.

## 3. Chi phí thực tế cần đo ở đâu?

Một ứng dụng modular vẫn có chi phí ở nhiều giai đoạn, nhưng cần xác định đúng giai đoạn trước khi tối ưu.

| Khu vực | Công việc có thể phát sinh | Cách đánh giá |
| --- | --- | --- |
| Startup | Tìm module, đọc descriptor, resolve graph, tạo layer và nạp class đầu tiên | Đo thời gian từ lúc process bắt đầu đến readiness |
| Class loading | Tìm, đọc, verify và định nghĩa class | Dùng profiling hoặc log class loading khi phù hợp |
| Reflection | Tìm constructor/field/method, kiểm tra quyền truy cập và invoke | Đo đường reflection thực tế so với API trực tiếp |
| Service loading | Khám phá provider và khởi tạo implementation | Đo số provider, thời điểm load và chi phí khởi tạo |
| Request handling | Xử lý nghiệp vụ, I/O, allocation, lock và thuật toán | Profile hot path bằng dữ liệu đại diện |
| Deployment | Dung lượng runtime image, số file, startup environment | Đo kích thước artifact, cold start và thời gian cài/chạy |

Module resolution thường là chi phí khởi động, không phải chi phí lặp lại trên mỗi request. Nếu vấn đề là latency của request sau khi ứng dụng đã warm up, hãy profile code xử lý request trước khi thay đổi module descriptor.

Nếu vấn đề là cold start, hãy đo toàn bộ quá trình từ process start đến khi ứng dụng sẵn sàng nhận request. Đừng chỉ đo thời gian gọi `main` hoặc thời gian resolve một module rồi suy ra toàn bộ startup latency.

## 4. Giữ boundary không có nghĩa là tạo quá nhiều module nhỏ

Encapsulation tốt không đồng nghĩa với việc chia mọi package thành một module riêng. Module granularity cần phù hợp với đơn vị thay đổi, ownership, dependency và triển khai.

Một module thường hợp lý khi các package bên trong:

- Cùng phục vụ một capability hoặc một trách nhiệm nghiệp vụ rõ ràng.
- Có vòng đời thay đổi và phát hành tương đối đồng nhất.
- Có thể quản lý dependency như một đơn vị.
- Cần một public API ổn định cho các consumer khác.
- Có implementation details nên được giữ kín khỏi consumer.

Không nên tách thành hàng chục module chỉ để mỗi class có descriptor riêng. Quá nhiều module nhỏ có thể làm tăng chi phí quản lý dependency, cấu hình build, versioning, testing và packaging. Nó cũng có thể khiến thay đổi nội bộ thường xuyên buộc nhiều module phải cập nhật descriptor.

Ví dụ một module billing có thể chứa API, domain logic và persistence implementation:

~~~text
com.acme.billing/
  module-info.java
  com/acme/billing/api/
  com/acme/billing/domain/
  com/acme/billing/internal/
  com/acme/billing/persistence/
~~~

Descriptor chỉ export các package mà consumer cần:

~~~java
module com.acme.billing {
    requires com.acme.money;
    exports com.acme.billing.api;
}
~~~

Khi domain logic và persistence có nhu cầu ownership, release hoặc runtime isolation riêng, hãy cân nhắc tách chúng thành module khác. Quyết định dựa trên kiến trúc và vận hành, không dựa trên một giả định rằng càng nhiều module càng nhanh hoặc càng ít module càng nhanh.

## 5. Đừng mở rộng public surface để tránh xử lý dependency

Một cách "tối ưu" sai thường gặp là export tất cả package hoặc mở toàn bộ module để framework và consumer có thể truy cập tùy ý.

Ví dụ:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.internal;
    exports com.acme.orders.persistence;
    opens com.acme.orders;
}
~~~

Cấu hình này làm public surface lớn hơn mức cần thiết. Consumer có thể bắt đầu phụ thuộc vào implementation class, repository hoặc chi tiết persistence. Framework cũng có thể deep-reflect vào những package không cần thiết.

Thiết kế chặt hơn:

~~~java
module com.acme.orders {
    requires com.acme.money;

    exports com.acme.orders.api;
    opens com.acme.orders.persistence to org.example.orm;
}
~~~

Nếu chỉ một module cần truy cập SPI, dùng qualified export:

~~~java
exports com.acme.orders.spi to com.acme.integration;
~~~

Nếu framework cần deep reflection, mở đúng package và đúng target module. Không dùng `ALL-UNNAMED` nếu framework đang chạy dưới một named module và có thể chỉ định tên module đó.

Giữ exports và opens tối thiểu giúp bảo vệ khả năng thay đổi implementation. Nó cũng làm cho lỗi dependency và lỗi reflection dễ truy vết hơn vì quyền truy cập được khai báo rõ.

## 6. Tránh gộp module chỉ để loại bỏ một dependency

Giả sử `com.acme.orders` dùng kiểu `Money` từ `com.acme.money`. Nếu kiểu đó xuất hiện trong public API, dependency nên được thể hiện rõ:

~~~java
module com.acme.orders {
    requires transitive com.acme.money;
    exports com.acme.orders.api;
}
~~~

Nếu chỉ dùng kiểu money trong implementation nội bộ, có thể dùng dependency thông thường:

~~~java
module com.acme.orders {
    requires com.acme.money;
    exports com.acme.orders.api;
}
~~~

Chọn `requires transitive` khi consumer của orders cần readability tới module money do kiểu của money xuất hiện trong public API. Không thêm transitive chỉ để "cho mọi thứ chạy".

Việc gộp hai module để bỏ một dòng `requires` có thể khiến module sở hữu quá nhiều trách nhiệm và làm mờ quyền sở hữu API. Một dependency rõ ràng thường là chi phí kiến trúc thấp hơn nhiều so với việc mất ranh giới giữa hai capability có thể thay đổi độc lập.

Trước khi gộp, hãy hỏi: hai module có thực sự cùng một ownership và vòng đời không? Chúng có cần phát hành hoặc kiểm thử độc lập không? Consumer có cần một API ổn định giữa chúng không? Nếu câu trả lời cho thấy boundary có ý nghĩa, hãy giữ dependency và đo chi phí thật nếu nghi ngờ hiệu năng.

## 7. Tối ưu startup và module resolution đúng cách

Nếu profiling cho thấy startup là vấn đề, có thể xem xét các giải pháp phù hợp với giai đoạn khởi động:

- Giảm công việc nặng trong static initializer và constructor chạy khi khởi động.
- Trì hoãn khởi tạo component chỉ dùng trong một số đường đi.
- Tránh tạo module layer/plugin graph mới nhiều lần nếu không cần thiết.
- Tránh quét classpath hoặc module path rộng để tìm component khi đã biết danh sách module cần dùng.
- Kiểm soát số lượng provider được khám phá nếu ứng dụng sử dụng `ServiceLoader`.
- Dùng runtime image phù hợp để loại bỏ module Java platform không cần thiết.

Nếu ứng dụng tạo plugin layer động, hãy đo chi phí của việc resolve configuration, tạo class loader và khởi tạo plugin. Giữ một layer cho mỗi plugin chỉ khi isolation hoặc vòng đời yêu cầu điều đó; không tạo layer mới cho mỗi request.

Không nên xóa `requires` hoặc bỏ service declaration chỉ để làm graph trông nhỏ hơn nếu code vẫn cần capability tương ứng. Dependency graph phải phản ánh các kiểu và service mà ứng dụng thực sự sử dụng.

## 8. Tối ưu runtime image mà vẫn giữ module boundary

Với modular application, `jlink` có thể tạo runtime image chỉ chứa các module Java platform cần thiết và dependency được chọn. Điều này thường hữu ích cho dung lượng triển khai, kiểm soát runtime và giảm yêu cầu cài đặt JDK đầy đủ.

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.app   --strip-debug   --no-header-files   --no-man-pages   --output runtime-image
~~~

Trên Windows, dùng path separator `;` thay cho `:` và đường dẫn JDK tương ứng.

Có thể yêu cầu liên kết service provider nếu ứng dụng cần các provider được bind:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.app   --bind-services   --output runtime-image
~~~

Sau đó dùng runtime image với `jpackage`:

~~~bash
jpackage --type app-image   --name AcmeOrders   --dest dist   --runtime-image runtime-image   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Việc loại bỏ module Java platform không dùng có thể giảm kích thước runtime image. Nó không đòi hỏi phải export mọi package hoặc gộp các module ứng dụng. Hãy kiểm tra service loading, reflection, charset, logging, TLS, native library và các đường chạy ít gặp trước khi phát hành image rút gọn.

Không được suy ra rằng runtime image nhỏ hơn chắc chắn làm mọi request nhanh hơn. Dung lượng triển khai, thời gian tải runtime, memory footprint và throughput là các chỉ số khác nhau; cần đo riêng.

## 9. Reflection không phải lý do để xóa encapsulation

Reflection có thể cần thiết cho framework, nhưng không nên mở mọi package để tránh cấu hình.

Ví dụ mở một package persistence cho ORM:

~~~java
module com.acme.orders {
    requires org.example.orm;

    exports com.acme.orders.api;
    opens com.acme.orders.persistence to org.example.orm;
}
~~~

Nếu framework nằm trên class path, JVM option có thể là:

~~~bash
--add-opens com.acme.orders/com.acme.orders.persistence=ALL-UNNAMED
~~~

Dùng `--add-opens` khi cần hỗ trợ runtime hoặc thư viện chưa thể khai báo qualified opens trong module descriptor. Hãy ghi lại lý do, target và package cụ thể để có thể rà soát khi nâng cấp framework.

Nếu reflection xảy ra trong hot path, hãy đo riêng chi phí tìm member, access check và invoke. Có thể cache metadata hoặc chuyển sang API trực tiếp khi thiết kế cho phép. Tuy nhiên, đừng thay đổi module boundary trước khi biết phần nào của reflection đang gây chi phí và có thể thay thế an toàn.

## 10. Đo hiệu năng thay vì suy luận từ số lượng module

Khi cần so sánh hai thiết kế, hãy tạo benchmark đại diện:

- Cùng workload, dữ liệu đầu vào và số lượng request.
- Cùng phiên bản JDK, JVM flags và phần cứng.
- Warm-up phù hợp trước khi lấy số liệu.
- Đo throughput, latency phân vị, allocation và memory footprint.
- Đo cold start riêng với steady-state.
- Lặp lại đủ lần để nhận biết nhiễu và biến động môi trường.

JMH phù hợp cho microbenchmark JVM khi cần đo một thao tác nhỏ như method call, lookup hoặc reflection. Đối với startup và packaging, dùng phép đo end-to-end trên process mới thay vì cố suy ra từ microbenchmark.

Không nên benchmark một method call đơn lẻ rồi kết luận toàn bộ kiến trúc module là nhanh hoặc chậm. Hiệu năng thực tế thường bị chi phối bởi I/O, lock contention, allocation, thuật toán, database hoặc network trước khi module resolution trở thành vấn đề.

Khi so sánh class path với module path, hãy giữ workload và runtime tương đương. Kết quả đo ở một ứng dụng cụ thể không chứng minh rằng một cơ chế luôn nhanh hơn trong mọi ứng dụng.

## 11. Triển khai có kiểm soát boundary

Trước khi phát hành, xác nhận artifact vẫn giữ đúng descriptor và hành vi:

1. Kiểm tra `module-info.class` của từng modular JAR.
2. Dùng `jar --describe-module` để xem `requires`, `exports`, `opens`, `uses` và `provides`.
3. Chạy ứng dụng bằng module path như môi trường production dự kiến.
4. Nếu dùng `jlink`, kiểm tra danh sách module trong runtime image và thử các service/provider cần thiết.
5. Nếu dùng `jpackage`, chạy launcher từ app image hoặc installer đã cài.
6. Kiểm tra framework reflection, cấu hình JVM option, resource và native library.
7. Đo startup, memory và workload quan trọng trên artifact cuối cùng.

Có thể xem descriptor:

~~~bash
jar --describe-module --file mods/com.acme.orders.jar
~~~

Có thể kiểm tra dependency:

~~~bash
jdeps --module-path mods --check com.acme.orders
~~~

Những lệnh này giúp kiểm tra metadata và dependency. Chúng không thay thế việc chạy integration test hoặc đo hiệu năng trên artifact được phân phối.

## 12. Khi nào nên thay đổi boundary?

Có thể cân nhắc thay đổi boundary khi:

- Hai module có cùng ownership và vòng đời, đồng thời việc tách gây dependency vòng hoặc cấu hình không cần thiết.
- Một package export không còn consumer và có thể đóng lại sau khi xác nhận tương thích.
- Một module đang expose implementation type ngoài ý muốn.
- Plugin cần isolation và vòng đời riêng nên cần layer hoặc module boundary rõ hơn.
- API public cần được tách khỏi implementation để giảm coupling.

Không nên thay đổi chỉ vì:

- Có thêm một dòng `requires`.
- Số lượng module nhìn có vẻ nhiều.
- Có một giả định chưa đo rằng method call giữa module chậm.
- Framework báo lỗi reflection và giải pháp được đề xuất là mở toàn bộ module.
- Runtime image lớn nhưng chưa phân tích module nào thực sự được dùng.

Một boundary tốt phải phục vụ ownership, API stability, dependency và khả năng triển khai. Nếu boundary không còn phản ánh kiến trúc, hãy điều chỉnh có chủ đích; nếu boundary vẫn có ích, tối ưu phần startup, runtime, reflection hoặc packaging đang được đo là tốn kém.

## Ghi nhớ

JPMS module boundary chủ yếu quản lý dependency và quyền truy cập trong cùng JVM; nó không biến mỗi method call thành lời gọi qua mạng. Module resolution thường ảnh hưởng startup, trong khi reflection, service loading và xử lý nghiệp vụ có chi phí riêng. Hãy đo đúng giai đoạn, chọn module granularity theo ownership và vòng đời, giữ exports/opens tối thiểu, và tối ưu runtime image bằng `jlink`/ `jpackage` khi phù hợp. Không xóa boundary cần thiết chỉ dựa trên giả định hiệu năng.
