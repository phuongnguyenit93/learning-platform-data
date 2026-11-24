# Vai trò triển khai pipeline của Spring Cloud Data Flow và giới hạn phạm vi

Trong một hệ thống xử lý sự kiện, Spring Cloud Stream là framework để viết ứng dụng kết nối với Kafka, RabbitMQ hoặc binder khác thông qua các hàm `Supplier`, `Function` và `Consumer`. Khi cần triển khai nhiều ứng dụng nguồn, xử lý và đích thành một pipeline liên tục, **Spring Cloud Data Flow (SCDF)** có thể hỗ trợ đăng ký artifact, mô tả topology, triển khai các tiến trình, quản lý phiên bản và quan sát trạng thái của chúng.

SCDF **không phải** thư viện cần thêm vào mọi dự án Spring Cloud Stream. Một ứng dụng Spring Cloud Stream vẫn chạy độc lập qua `java -jar`, container, Kubernetes Deployment hoặc nền tảng khác. SCDF là lớp điều phối triển khai *tùy chọn* đặt phía trên các ứng dụng đã được đóng gói. Nó không thay thế broker, không thực thi logic `Function` thay ứng dụng và không tự bảo đảm exactly-once, retry hay tính nhất quán dữ liệu.

**Lưu ý về vòng đời sản phẩm:** Spring thông báo ngày **21/04/2025** rằng Spring Cloud Data Flow, Spring Cloud Deployer và Spring Statemachine sẽ không tiếp tục được duy trì như các dự án mã nguồn mở. **SCDF 2.11.x là nhánh OSS cuối**; các bản phát hành tiếp theo chỉ dành cho khách hàng Tanzu Spring theo mô hình thương mại. Khi quyết định dùng SCDF trong dự án mới, cần đánh giá quyền sử dụng, đường nhận bản vá bảo mật, tương thích phiên bản và lựa chọn thay thế. Việc này **không có nghĩa Spring Cloud Stream ngừng mã nguồn mở**.

## 1. Phân biệt framework xử lý sự kiện với nền tảng triển khai

| Thành phần | Chịu trách nhiệm chính | Không làm thay |
|---|---|---|
| **Spring Cloud Stream** | Khai báo input/output binding; viết `Supplier`, `Function`, `Consumer`; dùng binder để trao đổi message | Không tự quản lý toàn bộ vòng đời nhiều ứng dụng |
| **Kafka/RabbitMQ/Pulsar** | Lưu chuyển/phân phối message theo cơ chế broker tương ứng | Không quyết định cách triển khai mã Java |
| **Spring Cloud Data Flow** | Đăng ký app, mô tả pipeline, khởi tạo deployment, quản lý release và quan sát pipeline | Không xử lý từng message trong data path |
| **Spring Cloud Skipper** | Quản lý vòng đời release stream, nâng cấp/rollback theo mô hình SCDF/Skipper | Không phải message broker |
| **Spring Cloud Deployer / nền tảng** | Tạo tiến trình hoặc workload thực trên local, Kubernetes, Cloud Foundry theo cấu hình | Không thay thế binder và message semantics |
| **Spring Cloud Task / Batch** | Chạy công việc hữu hạn; lưu trạng thái execution và xử lý batch | Không tương đương stream liên tục |

SCDF tổ chức *các ứng dụng triển khai được*; Spring Cloud Stream điều khiển luồng dữ liệu *bên trong mỗi ứng dụng*. Điểm phân biệt này giúp tránh nhầm lẫn khi xử lý sự cố: lỗi kết nối Kafka thường phải kiểm tra binder và broker, không chỉ trạng thái SCDF; lỗi tạo pod lại có thể nằm ở deployer, registry hoặc Kubernetes.

## 2. Kiến trúc control plane và data plane

~~~mermaid
flowchart TB
    subgraph Control["Control plane: triển khai và quản lý"]
      Operator[Developer / Operator] --> SCDF[SCDF Server + Shell / UI / REST]
      SCDF --> Registry[App registry: Maven / OCI image]
      SCDF --> Skipper[Skipper: stream release lifecycle]
      Skipper --> Platform[Kubernetes / Cloud Foundry / local deployer]
    end
    subgraph Data["Data plane: xử lý sự kiện"]
      Source[Source: Supplier / HTTP ingestion]
      Processor[Processor: Function]
      Sink[Sink: Consumer]
      Broker[(Kafka / RabbitMQ)]
      Source --> Broker
      Broker --> Processor
      Processor --> Broker
      Broker --> Sink
    end
    Platform -. starts / updates .-> Source
    Platform -. starts / updates .-> Processor
    Platform -. starts / updates .-> Sink
~~~

**Control plane** nhận yêu cầu từ người vận hành, giải quyết artifact, kết nối ứng dụng theo khai báo và ra lệnh nền tảng triển khai. **Data plane** gồm các ứng dụng Spring Boot đang chạy và broker mà chúng gửi/nhận message. Message không đi xuyên qua SCDF Server cho mỗi lần xử lý.

Nếu SCDF Server tạm không sẵn sàng nhưng các ứng dụng, broker và nền tảng vẫn hoạt động, pipeline đang chạy nhìn chung có thể tiếp tục xử lý. Ngược lại, SCDF không thể tự sửa một consumer sai schema hoặc broker bị mất quorum. SCDF cần hoạt động trở lại khi muốn thay đổi định nghĩa, nâng cấp, rollback hoặc xem trạng thái qua giao diện quản trị.

## 3. Các khối Source, Processor và Sink

Trong mô hình pipeline, mỗi bước thường đóng gói thành một ứng dụng Spring Boot riêng:

- **Source:** thu nhận dữ liệu từ HTTP, file, scheduler hoặc dịch vụ ngoài rồi gửi message tới broker. `Supplier<T>` là kiểu hàm điển hình; source cũng có thể dùng `StreamBridge` hoặc integration khác.
- **Processor:** nhận một message, chuyển đổi/lọc/bổ sung dữ liệu và phát message mới, thường là `Function<I,O>`.
- **Sink:** nhận message và thực hiện đầu ra cuối, như ghi database, audit hoặc gọi dịch vụ khác; thường là `Consumer<T>`.

Ví dụ nghiệp vụ:

~~~text
order-source | normalize-order | persist-order
    |               |                  |
  Supplier       Function            Consumer
    |               |                  |
    +-- Kafka topic A --> Kafka topic B --> database
~~~

Dấu `|` trong SCDF Stream DSL biểu diễn các ứng dụng tách biệt, nói chuyện qua messaging middleware. Không nhầm nó với `spring.cloud.function.definition=first|second`: dấu `|` trong Spring Cloud Function ghép các hàm chạy **trong cùng một ứng dụng/JVM**. Hai cơ chế có phạm vi triển khai, điều hành và failure domain khác nhau.

Ứng dụng có nhiều input/output, fan-out, topic động hoặc các topology Kafka Streams phức tạp không nhất thiết phù hợp với mô hình một input/một output của Stream DSL truyền thống. Với trường hợp đó, có thể dùng Stream Application DSL và khai báo binding rõ ràng, hoặc tự triển khai các ứng dụng mà không dùng SCDF.

## 4. Quy trình triển khai một stream bằng SCDF

Theo vòng đời SCDF/Skipper, quy trình thông thường gồm:

1. **Build và publish** ứng dụng Spring Boot thành Maven artifact hoặc OCI image.
2. **Register** từng artifact dưới tên và loại ứng dụng: `source`, `processor`, `sink`.
3. **Create** stream definition bằng DSL, chưa đồng nghĩa với việc khởi chạy các ứng dụng.
4. **Deploy** stream lên một platform đã cấu hình.
5. **Inspect/monitor** trạng thái ứng dụng, group, broker và kết quả xử lý.
6. **Update / rollback** ứng dụng trong stream theo release/version đã đăng ký.
7. **Undeploy** để dừng workload; **destroy** để xóa định nghĩa khi không còn sử dụng.

Việc register artifact chỉ cho SCDF biết artifact nằm ở đâu, không tự tạo container. Tương tự, lệnh create lưu định nghĩa pipeline; deploy mới ra lệnh chạy workload. Cần phân biệt ba trạng thái này khi viết pipeline CI/CD và runbook.

## 5. Đăng ký ứng dụng bằng Maven hoặc OCI image

SCDF nhận application artifact từ các repository mà server/deployer truy cập được. Với Kubernetes, định dạng Docker image là lựa chọn thường gặp; local deployment cũng có thể dùng Maven artifact tùy cấu hình.

Ví dụ lệnh trong **Spring Cloud Data Flow Shell** (không phải Bash trực tiếp):

~~~text
dataflow:> app register --name order-source --type source --uri docker://registry.example.com/event/order-source:1.0.0
dataflow:> app register --name normalize-order --type processor --uri docker://registry.example.com/event/normalize-order:1.0.0
dataflow:> app register --name persist-order --type sink --uri docker://registry.example.com/event/persist-order:1.0.0

dataflow:> app list
~~~

Các image URI ở đây chỉ là placeholder, không phải artifact có thật. Registry cần cấp quyền pull cho platform được SCDF/Skipper điều khiển. Phiên bản Spring Boot và Spring Cloud Stream bên trong từng image phải tương thích với binder, JDK, broker và cơ chế wiring mà SCDF đang sử dụng.

Một ví dụ Maven URI:

~~~text
dataflow:> app register --name normalize-order --type processor --uri maven://com.example:normalize-order:1.0.0
~~~

Không sửa nội dung ở cùng một image tag hoặc Maven coordinate rồi kỳ vọng SCDF tự lấy được bytes mới: registry/deployer có thể cache artifact. Sử dụng version hoặc image digest bất biến, đăng ký version mới và triển khai theo quy trình update/rollback.

Nếu đã có các ứng dụng tích hợp sẵn và tương thích, có thể import nhiều bản đăng ký từ một file properties theo định dạng `source.name=URI`, `processor.name=URI`, `sink.name=URI`. Không mặc định bất kỳ catalog ứng dụng cũ nào cũng còn tương thích với Spring Boot và Spring Cloud Stream mới.

## 6. Tạo, triển khai và xem trạng thái stream

Sau khi đăng ký ba application, định nghĩa pipeline:

~~~text
dataflow:> stream create --name orderPipeline --definition "order-source | normalize-order | persist-order"
dataflow:> stream info orderPipeline
~~~

Định nghĩa trên thể hiện **topology logic**. Khi deploy, SCDF gán destination cho các cặp output/input liền nhau để message có thể đi qua broker chung. Các app vẫn phải được cấu hình binder phù hợp và được broker chấp nhận kết nối.

Với các app dùng kiểu `Supplier`, `Function`, `Consumer` hiện đại, cần bảo đảm tên binding mà SCDF DSL truyền thống hiểu là `input`/`output` được ánh xạ chính xác. Ví dụ triển khai sau là một *mẫu*; tên bean thực phải khớp code trong từng image:

~~~text
dataflow:> stream deploy --name orderPipeline --properties "app.order-source.spring.cloud.stream.function.bindings.publishOrder-out-0=output,app.normalize-order.spring.cloud.stream.function.bindings.normalizeOrder-in-0=input,app.normalize-order.spring.cloud.stream.function.bindings.normalizeOrder-out-0=output,app.persist-order.spring.cloud.stream.function.bindings.persistOrder-in-0=input"
~~~

Trong đó:

- `publishOrder` phải là bean `Supplier` trong ứng dụng `order-source`.
- `normalizeOrder` phải là bean `Function` trong ứng dụng `normalize-order`.
- `persistOrder` phải là bean `Consumer` trong ứng dụng `persist-order`.
- Các property `app.<app-name>....` được chuyển cho từng app khi deploy.
- `spring.cloud.stream.function.bindings.<implicit-name>=input/output` đổi tên binding hàm về convention mà SCDF Stream DSL truyền thống sử dụng.

Một số ứng dụng SCDF mẫu đã đặt sẵn alias `input`/`output` và không cần khai báo lại. Ngược lại, một ứng dụng viết mới chỉ có `normalizeOrder-in-0`/`normalizeOrder-out-0` **không được giả định tự tương thích** với mọi phiên bản SCDF. Kiểm thử bằng broker thật và kiểm tra destination được gán cho hai đầu là bắt buộc.

Với nhiều property dài, nên lưu ở một file deployment properties được kiểm soát thay vì ghi tất cả trên dòng shell. Không đặt credential dưới dạng plain text trong lịch sử shell; dùng secret injection hoặc platform-specific credential mapping.

## 7. Ví dụ functional code tương ứng với ba app

Ba đoạn Java sau minh họa phần logic cốt lõi; mỗi bean thuộc một **Spring Boot application độc lập** đã đóng gói/đăng ký riêng. Chúng không phải ba bean chạy trong cùng một application context khi SCDF triển khai ba mắt xích.

**Source** (`order-source`):

~~~java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SourceConfiguration {

    @Bean
    Supplier<String> publishOrder() {
        return () -> "order-created";
    }
}
~~~

**Processor** (`normalize-order`):

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ProcessorConfiguration {

    @Bean
    Function<String, String> normalizeOrder() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

**Sink** (`persist-order`):

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SinkConfiguration {

    @Bean
    Consumer<String> persistOrder() {
        return event -> System.out.println("Accepted: " + event);
    }
}
~~~

Trong thực tế, `Supplier` phải đọc nguồn dữ liệu thật hoặc có cơ chế phát định kỳ; mặc định poller có thể kích hoạt supplier theo lịch. `Consumer` phải ghi bền vững hoặc thực hiện thao tác cuối có kiểm soát, không chỉ in log. Ví dụ cố ý dùng `String` để tập trung vào kiến trúc triển khai; khi dùng JSON, Avro hay Protobuf cần thêm schema, serializer và contract phù hợp ở mọi mắt xích.

SCDF không tự sinh code của ba ứng dụng và không sửa lỗi nghiệp vụ của chúng. Nhóm phát triển vẫn phải build, kiểm thử, version và bảo trì từng ứng dụng.

## 8. App properties và deployer properties khác nhau

SCDF có hai nhóm thuộc tính quan trọng trong deployment:

| Nhóm | Ý nghĩa | Ví dụ |
|---|---|---|
| `app.<app>.<property>` | Truyền cấu hình Spring Boot/Spring Cloud Stream vào application | `app.normalize-order.spring.cloud.function.definition=normalizeOrder` |
| `deployer.<app>.<property>` | Yêu cầu platform deployer điều khiển số instance hoặc tài nguyên | `deployer.normalize-order.count=2` |

Ví dụ triển khai trên platform hỗ trợ `count`:

~~~text
dataflow:> stream deploy --name orderPipeline --properties "deployer.normalize-order.count=2,app.normalize-order.spring.cloud.function.definition=normalizeOrder"
~~~

Lệnh này chỉ minh họa cú pháp nhóm property và giả định app đã đăng ký/wiring đúng; khi dùng trong thực tế còn phải truyền alias function binding như mục trước nếu cần.

Không dùng app property để kỳ vọng tăng số Kubernetes pod; cũng không dùng deployer property để cấu hình serializer hoặc retry cho Kafka binder. Tên thuộc tính tài nguyên chi tiết khác nhau giữa local, Kubernetes, Cloud Foundry deployer và từng phiên bản SCDF/Skipper; phải tham chiếu tài liệu platform tương ứng.

## 9. SCDF đóng góp điều gì khi dùng Kubernetes?

Khi SCDF/Skipper được cấu hình để triển khai lên Kubernetes, người vận hành có thể quản lý pipeline theo định nghĩa và release thay vì tự viết/sửa từng deployment ứng dụng.

SCDF/Skipper có thể hỗ trợ:

- Đăng ký và chọn version của từng source/processor/sink.
- Triển khai các workload theo platform configuration.
- Gán các thuộc tính input/output destination của Stream DSL.
- Chuyển app properties, deployer properties và lựa chọn platform.
- Kiểm tra trạng thái release/ứng dụng và thực hiện update/rollback.
- Quản lý việc undeploy/destroy stream theo vòng đời.

Kubernetes vẫn chịu trách nhiệm thực thi pod, scheduling, image pull, DNS, resource quota, network policy và restart theo controller. SCDF không trở thành Kubernetes control plane và không thay thế các cơ chế vận hành của cluster.

Đối với workload đơn giản chỉ có một hoặc hai microservice và các binding đã xác định, Kubernetes Deployment/Helm/GitOps có thể là giải pháp ít thành phần vận hành hơn SCDF. Nên cân đối lợi ích của mô hình pipeline DSL với chi phí triển khai một Data Flow Server, Skipper, database và lớp quản trị.

## 10. Nâng cấp và rollback qua Skipper

Trong kiến trúc SCDF 2.x, Skipper quản lý stream release và triển khai thay đổi ứng dụng theo version. Các ví dụ shell thường gặp:

~~~text
dataflow:> app register --name normalize-order --type processor --uri docker://registry.example.com/event/normalize-order:1.1.0
dataflow:> stream update --name orderPipeline --properties "version.normalize-order=1.1.0"
dataflow:> stream rollback --name orderPipeline
~~~

Phải đăng ký version mới trước khi update. Lệnh rollback có ý nghĩa ở mức release ứng dụng; nó không hoàn nguyên các message đã phát, side effect database, schema topic hoặc trạng thái giao dịch ngoài broker.

Không giả định phương án update của Skipper luôn giống rolling update native Kubernetes. Tùy phiên bản và platform, chiến lược có thể tạo phiên bản mới song song rồi chuyển đổi; lúc đó producer/consumer phiên bản cũ và mới có thể cùng hiện diện trong một khoảng thời gian.

Trước release, kiểm tra:

1. Compatibility của message schema khi old/new versions cùng chạy.
2. Tác động của rebalance tới consumer group và Kafka Streams task.
3. Idempotency nếu message được giao lại.
4. Cách rollout khi group/partition thay đổi.
5. Khả năng rollback schema và migration database.
6. Health, lag, DLQ, throughput và business outcome sau deploy.

SCDF tạo điều kiện quản trị release; nó **không** là một bảo đảm an toàn nâng cấp end-to-end.

## 11. Undeploy và destroy là hai thao tác khác nhau

~~~text
dataflow:> stream undeploy --name orderPipeline
dataflow:> stream destroy --name orderPipeline
~~~

**Undeploy** dừng các workload đang chạy của pipeline nhưng có thể giữ lại định nghĩa stream để deploy tiếp. **Destroy** xóa định nghĩa/metadata stream khỏi SCDF theo quy trình sản phẩm; thường thực hiện sau khi stream đã được undeploy.

Thao tác này không đồng nghĩa với xóa topic Kafka, RabbitMQ queue, dữ liệu đã ghi trong sink hoặc database của ứng dụng. Việc xóa message broker resources là một quyết định vận hành riêng, có thể gây mất dữ liệu và tác động tới các consumer khác.

Khi dừng pipeline, backlog có thể tiếp tục tăng nếu upstream producer vẫn phát. Với hệ thống yêu cầu không mất sự kiện, cần kế hoạch dừng nguồn, drain backlog, quản lý retention và kiểm tra consumer offset trước khi undeploy.

## 12. Vai trò của binder và broker trong pipeline

SCDF chỉ kết nối topology logic. Truyền message thật cần binder và broker:

~~~text
App A                         App B
Supplier                       Function
  |                              ^
  v                              |
output binding --- Kafka topic --- input binding
                    |
                 partitions
~~~

Các điều kiện phải đồng thời đúng:

- Mỗi app có dependency binder tương thích với broker được chọn.
- Hai đầu kết nối dùng cùng destination, protocol/schema và cấu hình broker phù hợp.
- Consumer group được đặt đúng để nhiều instance chia tải mà không nhận trùng theo mục đích.
- Partition count, partition key và serializer phù hợp nếu cần ordering/co-partitioning.
- TLS/SASL/credential được cấu hình và quyền truy cập broker được cấp.
- Retry, DLQ, error handling và acknowledgement semantics được kiểm tra ở **ứng dụng/binder**.

SCDF có thể truyền cấu hình qua deployment properties, nhưng nó không tự biến một image dùng Kafka binder thành Rabbit binder nếu image không có dependency và cấu hình thích hợp. Với ứng dụng nhiều binder, phải đặt binder cho từng binding và đảm bảo các broker thực sự tương thích với data path đã định nghĩa.

Nếu cần chuyển đổi Kafka sang RabbitMQ, một processor bridge có cả hai binder hoặc một connector phù hợp có thể cần thiết. Một dấu `|` trong DSL không tự chuyển đổi giao thức broker.

## 13. Giới hạn: không thay thế business logic và tính đúng của dữ liệu

SCDF không chịu trách nhiệm thực thi logic mapping, filtering, enrichment, windowing, schema validation hay idempotency của ứng dụng. Các trách nhiệm đó thuộc Spring Cloud Stream function, Kafka Streams topology hoặc dịch vụ nghiệp vụ riêng.

Ví dụ:

- `normalizeOrder` nhận JSON sai schema: lỗi xảy ra tại consumer deserializer/function và cần policy retry/DLQ.
- Khóa Kafka partition không ổn định: ordering có thể bị phá; SCDF không sửa partition key.
- Sink ghi dữ liệu trùng khi redelivery: cần idempotency/inbox ở sink.
- Kafka Streams state restore chậm: cần cấu hình state store/changelog, CPU/memory/disk và probes phù hợp.
- Một API downstream không sẵn sàng: cần timeout, backoff, circuit breaker hoặc outbox tùy kiến trúc.

Quản lý deployment tốt không đồng nghĩa với bảo đảm giao nhận end-to-end. Chọn at-least-once, transaction hoặc deduplication theo nhu cầu nghiệp vụ; kiểm thử crash giữa side effect và commit/ack.

## 14. Giới hạn: một stream DSL không mô tả được mọi topology

Stream DSL dạng `source | processor | sink` thuận tiện cho chuỗi tuyến tính. Nhưng Spring Cloud Stream hỗ trợ nhiều cấu trúc khác:

- Một function nhận nhiều input hoặc phát nhiều output.
- Dynamic destination qua `StreamBridge`.
- Kafka Streams join giữa KStream và KTable/GlobalKTable.
- Consumer topology có nhánh hoặc xử lý stateful.
- Nhiều binder, nhiều cluster với partitioning khác nhau.

Với nhiều input/output, Data Flow **không thể tự đoán** output nào nối vào input nào. Stream Application DSL dùng `||` để biểu thị trường hợp không tự thiết lập các binding như DSL tuyến tính, rồi ứng dụng/đề bài phải cấu hình destination và binder thủ công. Không dùng `||` như một phép join message; nó liên quan đến cách khai báo/deploy ứng dụng, không phải một toán tử Kafka Streams.

SCDF còn có loại đăng ký application tên `app` dành cho Stream Application DSL. Loại này có thể là ứng dụng Spring Boot thông thường, không nhất thiết dùng Spring Cloud Stream; SCDF không tự cấu hình input/output binding của nó như với source/processor/sink trong pipeline `|`. Do đó, khi dùng `||` với app có nhiều binding, trách nhiệm đặt destination và kiểm thử data path thuộc về người thiết kế pipeline.

Khi pipeline chứa nhiều nhánh phức tạp, có thể chia thành nhiều stream riêng, đặt tên destination rõ ràng, hoặc dùng Kubernetes manifests/Helm để triển khai. Mức hỗ trợ DSL và binding phụ thuộc version SCDF/SCSt đang dùng.

## 15. Giới hạn: SCDF không thay message broker hoặc runtime scheduler

Không nhầm ba hoạt động:

| Câu hỏi | Thành phần quyết định |
|---|---|
| Message được lưu ở đâu và giữ bao lâu? | Kafka/RabbitMQ/Pulsar và cấu hình broker |
| Hàm nào xử lý message? | Spring Cloud Stream application |
| App nào được triển khai, version nào, bao nhiêu instance? | SCDF/Skipper/deployer + platform |
| Pod/tiến trình chạy trên node nào? | Kubernetes/Cloud Foundry/local runtime |
| Khi nào offset được commit hoặc message được ack? | Binder, client/container và transaction/ack policy |
| Task hoặc batch job hữu hạn chạy khi nào? | SCDF Task/Scheduler + Spring Cloud Task/Batch và platform |

Với **stream**, ứng dụng thường là long-running workload, message kích hoạt xử lý liên tục. Với **task/batch**, ứng dụng có điểm bắt đầu và kết thúc; SCDF có thể khởi chạy và ghi nhận lịch sử execution của Spring Cloud Task/Batch. Pipeline stream không trở thành batch job chỉ vì được tạo bằng SCDF.

Không dùng stream DSL như engine ETL chạy trong một process hoặc scheduler đảm bảo message ordering. Nếu cần workflow có bước điều kiện, compensation, human approval hoặc DAG phức tạp, phải đánh giá một công cụ orchestration chuyên cho workflow/task.

## 16. Giới hạn khi triển khai nhiều môi trường và nhiều phiên bản

SCDF quản lý pipeline dựa trên các artifact đã đăng ký và platform được cấu hình. Nhưng ứng dụng vẫn phải được thiết kế cho môi trường triển khai:

- **Local:** thuận tiện để học và thử nghiệm; không phản ánh đầy đủ yêu cầu HA, network/security hay container orchestration.
- **Kubernetes:** cần registry access, namespace/RBAC, resource request/limit, secret, Service/DNS, probe và network policy.
- **Cloud Foundry:** cần đúng org/space, quota, service binding và deployment properties.

Không giả định URI `docker://...` phù hợp với mọi platform; một số deployer dùng Maven artifact hoặc cơ chế nhận artifact khác. Cũng không giả định image Spring Boot 3/4 hoặc Spring Cloud Stream 5 sẽ tương thích với bản SCDF 2.11 OSS cũ: kiểm tra ma trận support, cách inject binding properties và thực nghiệm với broker thật.

Tương tự, việc Spring Cloud Stream hoặc thư viện bên ngoài có một Pulsar binder không có nghĩa SCDF tự cung cấp catalog ứng dụng Pulsar, chuyển đổi giao thức hay support matrix tương ứng. Muốn đưa một app dùng Pulsar vào pipeline, cần xác minh bộ binder, triển khai và wiring thực tế có hoạt động với phiên bản SCDF đang dùng.

Đặc biệt, các ví dụ online cũ dùng `@EnableBinding`, `@StreamListener` hoặc binding tên `input`/`output`. Ứng dụng hiện đại theo functional model thường dùng `<functionName>-in-0`/`<functionName>-out-0`; để SCDF DSL truyền thống wiring đúng, cần alias hoặc cấu hình explicit như mục 6. Không sao chép cấu hình cũ mà bỏ qua sự khác biệt này.

## 17. Bảo mật management plane

SCDF Server, Skipper và platform deployer có quyền ảnh hưởng đến nhiều workload; bảo vệ chúng như các endpoint quản trị:

- Chỉ expose UI/REST/Shell qua mạng quản trị hoặc gateway đã xác thực.
- Dùng RBAC và nguyên tắc tối thiểu quyền đối với stream deploy/update/rollback/destroy.
- Phân tách quyền đọc trạng thái và quyền thay đổi pipeline.
- Lưu registry, broker và deployer credential trong secret store; không nhúng vào stream definition hoặc log lệnh.
- Kiểm tra image provenance, scan CVE và pin artifact digest/version.
- Ghi audit người thực hiện thay đổi, stream, app version, platform, thời điểm và kết quả.
- Kiểm soát egress của source/sink, network policy giữa app và broker.

Một người có quyền thay đổi stream có thể triển khai image mới, ảnh hưởng đến data path và khả năng truy cập dữ liệu. Vì vậy, không coi SCDF chỉ là dashboard quan sát. Đặc biệt tránh cấp quyền deploy rộng cho mọi developer trên cùng một production cluster.

## 18. Quan sát ở cả ba lớp

Một pipeline có trạng thái “deployed” chưa chắc đang xử lý đúng. Nên kết hợp ba lớp quan sát:

| Lớp | Chỉ báo |
|---|---|
| SCDF/Skipper | Stream definition, app version, deployment/rollout status, lỗi deployer |
| Runtime (Kubernetes/CF) | Pod/process health, restart, CPU/RAM, volume, readiness, image pull |
| Data path (binder/broker/app) | Consumer lag, topic/queue depth, throughput, retry, DLQ, deserialization error, state restore, business outcome |

Khi `stream deploy` báo thành công, thực hiện smoke test với message ID cụ thể: đưa dữ liệu vào source, xác nhận processor phát output rồi kiểm tra sink. Tránh dùng chỉ một health endpoint hoặc trạng thái release để kết luận pipeline không mất message.

Nếu pipeline có Kafka Streams stateful processor, việc pod Ready không tự chứng minh tất cả state store đã khôi phục. Cần thêm chỉ báo phù hợp với trạng thái ứng dụng và kiểm tra lag/restore. Khi scale in/out, theo dõi rebalance và task migration.

## 19. Chọn SCDF hay triển khai trực tiếp?

| Hoàn cảnh | Lựa chọn thường hợp lý | Lý do |
|---|---|---|
| Một Spring Cloud Stream consumer độc lập | Docker/Kubernetes/Cloud Foundry trực tiếp | Ít thành phần và thao tác hơn |
| Vài service với destination ổn định | Helm/GitOps hoặc manifest trực tiếp | Dễ quản lý bằng repo hiện có |
| Nhiều source/processor/sink tái sử dụng theo DSL | Cân nhắc SCDF nếu có phiên bản/support phù hợp | App registry, stream definition, lifecycle chung |
| Nhiều pipeline thay version thường xuyên | SCDF/Skipper hoặc nền tảng CD chuyên dụng | Có release management tập trung |
| State machine, workflow điều kiện, step orchestration | Công cụ workflow phù hợp | SCDF stream DSL không chuyên cho workflow DAG tùy ý |
| Tổ chức không có quyền bản vá SCDF thương mại | Ưu tiên đánh giá triển khai trực tiếp/giải pháp đang được hỗ trợ | Tránh phụ thuộc control plane OSS không còn duy trì |

SCDF có thể phù hợp với hệ thống đang vận hành có nhiều pipeline và cần quản lý tập trung. Nhưng để quyết định cho dự án mới, phải so sánh tổng chi phí sở hữu: cài đặt/HA, database, Skipper, security, artifact registry, training, hỗ trợ và nâng cấp phiên bản.

Chọn **không** dùng SCDF vẫn hoàn toàn có thể triển khai Spring Cloud Stream production. Nhóm phát triển tự cấu hình các output/input destination giống nhau, kết nối broker, consumer group, manifests, metrics và quy trình rollout.

## 20. Tình huống thực tế: tách hay gộp một pipeline?

Giả sử ứng dụng nhận đơn hàng, tính thuế rồi lưu báo cáo:

~~~text
HTTP/API source --> tax processor --> report sink
~~~

**Thiết kế A — một ứng dụng Spring Boot:** Một `Function` hoặc nhiều function ghép trong cùng JVM nhận message, tính thuế và lưu kết quả. Triển khai một container trực tiếp nếu workload nhỏ, vòng đời thay đổi đồng thời và không cần scale từng bước.

**Thiết kế B — ba ứng dụng độc lập không có SCDF:** Mỗi bước là một app Spring Cloud Stream, nối qua topic. Kubernetes/Helm triển khai ba workload; CI/CD cập nhật artifact và manifest. Phù hợp nếu đội có nền tảng triển khai sẵn và muốn kiểm soát rõ từng app.

**Thiết kế C — ba ứng dụng với SCDF:** Đăng ký ba app và mô tả pipeline bằng Stream DSL. SCDF/Skipper quản lý định nghĩa, deploy/update/rollback; binder vẫn đảm nhiệm message path. Phù hợp khi nhiều pipeline cùng dùng các ứng dụng tái sử dụng và tổ chức có quyền sử dụng/bảo trì SCDF.

Trong cả ba thiết kế, yêu cầu giao nhận, schema compatibility, idempotency và quyền truy cập dữ liệu vẫn phải giải quyết tại ứng dụng/broker. Không có một công cụ triển khai nào tự loại bỏ những yêu cầu này.

## 21. Checklist trước khi chọn và dùng SCDF

- Đã xác định rõ cần điều phối nhiều app hay chỉ cần triển khai một Spring Cloud Stream service.
- Đã kiểm tra tình trạng hỗ trợ/giấy phép của SCDF, Skipper, Deployer và đường nhận bản vá.
- Đã xác minh phiên bản Spring Boot, Spring Cloud Stream, binder và SCDF/Skipper tương thích.
- Các source/processor/sink được build, kiểm thử, version và đăng ký đúng loại artifact.
- Đã phân biệt register, create, deploy, update, rollback, undeploy và destroy.
- Với functional model, đã ánh xạ đúng `<function>-in-0/out-0` sang `input`/`output` nếu SCDF DSL cần.
- Với pipeline nhiều input/output, đã cấu hình destination thủ công thay vì để DSL đoán.
- App properties được tách khỏi deployer properties.
- Cả hai đầu của mỗi cạnh dữ liệu sử dụng broker, destination, schema và binder tương thích.
- Consumer group, partitioning, retry, DLQ và giao nhận được thiết kế ở ứng dụng/broker.
- Registry và management API được bảo vệ bằng authentication, RBAC và network policy.
- Rollout/rollback đã xét đến schema evolution, rebalance, side effect và dữ liệu đã xử lý.
- Có quan sát control plane, workload runtime và data plane riêng.
- Có phương án triển khai trực tiếp bằng Docker/Kubernetes nếu SCDF không phù hợp.

## Tổng kết

Spring Cloud Data Flow giúp **định nghĩa và triển khai nhiều ứng dụng Spring Cloud Stream thành pipeline**, quản lý artifact, platform và vòng đời release. Dữ liệu vẫn chảy trực tiếp giữa các ứng dụng qua broker; không đi qua SCDF Server. SCDF không tự viết business logic, không giải quyết mọi topology, không thay thế Kubernetes, Kafka/RabbitMQ/Pulsar và không bảo đảm message exactly-once hoặc rollback dữ liệu.

Vì SCDF đã dừng phát hành mã nguồn mở được duy trì từ năm 2025, việc đưa nó vào kiến trúc mới cần kiểm tra quyền hỗ trợ và tương thích sản phẩm trước khi đầu tư. Nếu nhu cầu chỉ là triển khai các ứng dụng Spring Cloud Stream độc lập, Docker, Kubernetes, Helm và GitOps thường là phương án trực tiếp, dễ kiểm soát hơn.

## Tài liệu tham khảo

- [Spring Cloud Data Flow Reference — Stream Introduction, Lifecycle, Skipper](https://docs.spring.io/spring-cloud-dataflow/docs/2.11.0/reference/htmlsingle/)
- [Spring Cloud Data Flow — Using Applications](https://dataflow.spring.io/docs/applications/)
- [Spring Cloud Data Flow — Functional Apps and Input/Output Binding Aliases](https://dataflow.spring.io/docs/recipes/functional-apps/scst-function-bindings/)
- [Spring Cloud Data Flow — Stream Application DSL](https://dataflow.spring.io/docs/feature-guides/streams/stream-application-dsl/)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Data Flow — Standalone Deployment Without Data Flow](https://dataflow.spring.io/docs/stream-developer-guides/streams/deployment/)
- [Spring Cloud Data Flow — FAQ: Runtime Independence](https://dataflow.spring.io/docs/resources/faq/)
- [Spring Blog, 21/04/2025 — Spring Cloud Data Flow End of Open-Source](https://spring.io/blog/2025/04/21/spring-cloud-data-flow-commercial/)
