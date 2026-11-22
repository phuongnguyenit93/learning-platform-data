# GraalVM native image và đánh giá startup trên GCP

Một ứng dụng Java và Spring Boot có thể chạy dưới dạng JVM truyền thống hoặc được biên dịch trước thành chương trình native bằng GraalVM Native Image. Hai cách triển khai này thường có đặc điểm khác nhau về thời gian khởi động, mức sử dụng bộ nhớ, thời gian build và hiệu năng khi xử lý tải lâu dài. Với Google Cloud, sự khác biệt trở nên đáng chú ý khi Cloud Run tạo instance để đáp ứng lưu lượng mới, GKE mở rộng số replica hoặc một tác vụ Java chỉ chạy trong thời gian ngắn.

Mục tiêu của bài học là hiểu Native Image và Spring AOT, tạo được hai biến thể từ cùng mã nguồn, triển khai chúng với điều kiện tương đương và đo startup theo cách có thể kiểm chứng. Quyết định chọn JVM hay native cần dựa trên dữ liệu của chính workload: giảm startup chỉ có ý nghĩa khi nó cải thiện độ trễ người dùng, khả năng scale hoặc chi phí tổng thể đủ để bù cho đánh đổi khi build và vận hành.

## 1. JVM truyền thống, AOT và Native Image khác nhau thế nào?

Với JVM, mã Java được biên dịch thành bytecode. Khi ứng dụng chạy, JVM nạp class, khởi tạo runtime, thực thi bytecode và có thể dùng Just-in-Time (JIT) compiler để tối ưu các đoạn mã được gọi nhiều. JVM có hệ sinh thái thư viện rộng và khả năng thích ứng tốt với hành vi động, nhưng quá trình khởi tạo và làm nóng JIT có thể góp phần làm tăng thời gian bắt đầu phục vụ.

GraalVM Native Image phân tích mã và các dependency tại thời điểm build, sau đó biên dịch trước thành một executable cho hệ điều hành và kiến trúc đích. Executable không cần khởi chạy một JVM HotSpot riêng khi chạy. Native Image vẫn có garbage collector và các dịch vụ runtime cần thiết, nhưng phần lớn công việc phân tích mã đã chuyển sang giai đoạn build.

| Tiêu chí | Ứng dụng chạy trên JVM | Ứng dụng Native Image |
| --- | --- | --- |
| Artifact | JAR cùng JRE/JDK hoặc container có Java runtime | Executable native cùng những thư viện hệ thống cần thiết |
| Biên dịch | Bytecode, có thể tối ưu bằng JIT khi chạy | Ahead-of-Time (AOT) tại thời điểm build |
| Startup | Có khởi tạo JVM và các thành phần ứng dụng | Thường khởi động nhanh hơn với cùng workload |
| Bộ nhớ khi chạy | Bao gồm heap Java, metadata và thành phần JVM | Thường có resident memory thấp hơn ở workload nhỏ |
| Thời gian và tài nguyên build | Thường ngắn hơn | Thường lâu hơn, dùng nhiều CPU/RAM khi biên dịch |
| Phản chiếu và tải mã động | Linh hoạt hơn | Cần mô tả trước khả năng truy cập động khi không được phân tích tự động |
| Hiệu năng tải dài | JIT có thể tối ưu đường đi nóng theo dữ liệu runtime | Hiệu năng phụ thuộc mã và cấu hình biên dịch native |

Các chữ "thường" là quan trọng: Native Image không bảo đảm luôn nhanh hơn hoặc ít RAM hơn trong mọi trường hợp. Ví dụ, một dịch vụ xử lý tính toán nặng và chạy liên tục có thể đạt throughput tốt hơn trên JVM đã warm up. Ngược lại, một API phục vụ lưu lượng thưa có thể hưởng lợi lớn từ thời gian khởi động ngắn.

## 2. Spring AOT tham gia vào quá trình biên dịch native

Spring Boot sử dụng các cơ chế động như quét component, proxy, serialization, reflection và điều kiện cấu hình. Các đặc điểm này làm framework linh hoạt trên JVM nhưng có thể khó phân tích hoàn toàn tại build time. Spring AOT xử lý cấu hình ứng dụng trước, tạo mã và gợi ý cần thiết để Native Image biết những thành phần nào phải xuất hiện trong executable.

Luồng xây dựng ở mức khái niệm:

~~~mermaid
flowchart LR
  S["Java source và dependencies"] --> C["Biên dịch Java"]
  C --> A["Spring AOT processing"]
  A --> N["GraalVM Native Image"]
  N --> I["Container native"]
  C --> J["Đóng gói JVM container"]
  I --> R["Cloud Run / GKE"]
  J --> R
  R --> M["Đo startup, latency, RAM và chi phí"]
~~~

Spring AOT có thể tạo cấu hình hỗ trợ một phần các trường hợp reflection phổ biến của Spring Boot, Jackson và các starter được hỗ trợ. Tuy nhiên, mã ứng dụng dùng Class.forName, reflection trực tiếp, thư viện plugin động, tạo proxy ở runtime hoặc tải resource bằng tên được tính toán vẫn có thể cần runtime hints bổ sung.

Native Image áp dụng nguyên tắc phân tích thế giới đóng (closed-world assumption) ở thời điểm build: những lớp, phương thức và resource không được phân tích là có thể cần đến sẽ không tự động xuất hiện khi chạy. Vì vậy, code chạy tốt trên JVM chưa chắc chạy đúng trong executable native nếu có đường thực thi động chỉ xuất hiện trong production.

## 3. Chọn workload phù hợp trước khi tối ưu

Native Image đáng được thử nghiệm khi startup và memory là phần đáng kể của chi phí hoặc trải nghiệm. Các tình huống phổ biến trên GCP:

- **Cloud Run scale to zero:** một request đến sau thời gian không có instance có thể phải chờ instance mới sẵn sàng.
- **Cloud Run workload dao động:** đột biến traffic khiến nền tảng tạo thêm instance và thời gian khởi động có thể góp phần vào độ trễ.
- **GKE autoscaling:** pod mới cần khởi động và đạt readiness trước khi nhận traffic.
- **Cloud Run Jobs hoặc batch ngắn:** startup chiếm tỷ lệ đáng kể trong tổng thời gian mỗi execution.
- **Ứng dụng với hạn mức bộ nhớ chặt:** giảm resident memory có thể giúp giảm memory allocation hoặc tăng mật độ workload.

Các trường hợp nên cân nhắc kỹ hơn gồm ứng dụng có dependency sử dụng nhiều reflection hoặc native libraries, hệ thống cần dynamic class loading, và dịch vụ tính toán chạy lâu với JIT đã tối ưu. Nếu traffic luôn ổn định và instance hiếm khi khởi động lại, giảm vài giây startup có thể không làm thay đổi nhiều trải nghiệm thực tế.

Trước khi triển khai thử nghiệm, xác định mục tiêu đo được, ví dụ: giảm p95 thời gian sẵn sàng của instance, giảm p95 request đầu tiên, giảm RAM trung bình hoặc rút ngắn thời gian scale out. Không nên lấy kích thước executable làm mục tiêu duy nhất.

## 4. Chuẩn bị ứng dụng Spring Boot và công cụ

Ví dụ trong bài sử dụng một ứng dụng Spring Boot hỗ trợ AOT/native, Java 21 và Maven Wrapper. Hãy chọn phiên bản Spring Boot, GraalVM và Native Build Tools tương thích với nhau theo tài liệu của phiên bản đang sử dụng. Native executable được tạo theo hệ điều hành và kiến trúc mà quá trình biên dịch nhắm đến; executable build cho máy phát triển không nhất thiết chạy trực tiếp trong Linux container.

Các điều kiện cần thiết:

1. Ứng dụng đã chạy và có kiểm thử hoạt động trên JVM.
2. Project có Spring Boot Maven Plugin và profile native từ cấu hình Spring Boot phù hợp; nếu không dùng Spring Boot parent, cần cấu hình plugin native tường minh.
3. Môi trường build có đủ CPU, RAM và dung lượng disk cho Native Image; tài nguyên build thường cao hơn lúc chạy.
4. Docker hoặc nền tảng container build có builder hỗ trợ native compilation.
5. Quyền truy cập Artifact Registry, Cloud Run hoặc GKE được cấp theo đúng principal dùng để build và deploy.

Ví dụ một đoạn Maven build khi project dùng Spring Boot parent:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin>
  </plugins>
</build>
~~~

Đây là phần build của một pom.xml, không phải pom.xml đầy đủ. Spring Boot parent và cấu hình plugin thực tế quyết định profile native có sẵn và cách resolve các phiên bản plugin. Với project chỉ dùng BOM hoặc build nhiều module, cần khai báo Native Build Tools và cấu hình native test/build phù hợp thay vì giả định parent đã cấu hình giúp.

Nếu ứng dụng dùng Gradle, Spring Boot Gradle Plugin và GraalVM Native Build Tools cung cấp các task liên quan như nativeCompile và bootBuildImage. Chỉ chọn một quy trình build chính để CI và máy phát triển cho kết quả nhất quán.

## 5. Tạo hai container để so sánh công bằng

Để biết Native Image có thực sự tốt hơn JVM cho ứng dụng, hãy giữ nguyên mã nguồn, dependency và cấu hình nghiệp vụ, chỉ thay đổi cách đóng gói/runtime.

Ví dụ build container JVM bằng Spring Boot buildpacks:

~~~bash
./mvnw -DskipTests spring-boot:build-image \
  -Dspring-boot.build-image.imageName=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-jvm:trial
~~~

Ví dụ build container native bằng buildpack hỗ trợ GraalVM Native Image:

~~~bash
./mvnw -Pnative -DskipTests spring-boot:build-image \
  -Dspring-boot.build-image.imageName=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-native:trial
~~~

Các câu lệnh là mẫu cho project Maven đã cấu hình hỗ trợ native và có Docker hoạt động. Tên project, repository và image là placeholder. Builder cần hỗ trợ native compilation; phiên bản builder/buildpack phải tương thích với Java và Spring Boot đã chọn. Nếu muốn tạo executable native trực tiếp trên máy có GraalVM và Native Build Tools, có thể dùng lệnh sau:

~~~bash
./mvnw -Pnative native:compile
~~~

Khi build native thất bại vì thiếu RAM hoặc hết thời gian, cần xem tài nguyên builder và log biên dịch trước khi sửa mã ứng dụng. Với CI, hãy đo riêng thời gian và tài nguyên build để biết chi phí tổng thể của việc chuyển sang Native Image.

Sau khi build, đẩy hai image lên Artifact Registry:

~~~bash
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
docker push asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-jvm:trial
docker push asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-native:trial
~~~

Không đưa credentials dài hạn vào image. Sử dụng service account hoặc Workload Identity Federation cho hệ thống CI khi có thể. Với production, ưu tiên deploy theo image digest và lưu thông tin commit, build ID, builder version để việc so sánh hoặc rollback có thể tái hiện.

## 6. Reflection, resource và runtime hints

Một trở ngại phổ biến là đường đi sử dụng reflection không được phát hiện khi biên dịch. Ví dụ, ứng dụng đọc tên class từ cấu hình rồi dùng reflection để tạo instance, hoặc thư viện cần nạp một file resource theo tên động.

Trong Spring, có thể đăng ký runtime hints cho thành phần thực sự cần truy cập động:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration
@ImportRuntimeHints(OrderNativeHints.class)
class NativeConfiguration {
}

class OrderNativeHints implements RuntimeHintsRegistrar {
  @Override
  public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
    hints.reflection().registerType(
        OrderPayload.class,
        MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
        MemberCategory.INVOKE_PUBLIC_METHODS);

    hints.resources().registerPattern("schemas/order-v1.json");
  }
}
~~~

Trong ví dụ, OrderPayload là lớp của ứng dụng và resource được đặt trong classpath tại schemas/order-v1.json. Đoạn mã cần được bổ sung lớp tương ứng trong project thực tế. Đăng ký chỉ những class và resource cần thiết, vì khai báo quá rộng làm giảm lợi ích phân tích tĩnh và khiến lỗi thiết kế khó phát hiện hơn.

Khi sửa lỗi native:

- Tìm stack trace đầu tiên có ý nghĩa tại thời điểm khởi động hoặc thực thi tính năng.
- Xác nhận lỗi là do reflection, resource, serialization, dynamic proxy, JNI hay thư viện chưa tương thích.
- Kiểm tra Spring AOT runtime hints sẵn có và reachability metadata của dependency trước khi thêm cấu hình thủ công.
- Tạo test thực thi đúng code path trong native image; không chỉ kiểm tra ứng dụng khởi động.
- Tránh dùng tùy chọn cho phép truy cập động một cách quá rộng nếu có thể khai báo cụ thể.

Đặc biệt, ứng dụng có thể khởi động thành công nhưng chỉ lỗi khi một endpoint ít dùng chạy lần đầu. Vì vậy, kiểm thử native cần bao phủ đường đi đăng nhập, serialization, truy cập database, secret, kết nối TLS và các thư viện quan trọng.

## 7. Định nghĩa startup trước khi đo

Từ "startup" có thể chỉ nhiều khoảng thời gian:

| Thước đo | Điểm bắt đầu và kết thúc | Giá trị đối với vận hành |
| --- | --- | --- |
| Application startup | Từ khi tiến trình Java/native bắt đầu đến khi Spring thông báo sẵn sàng | Đánh giá chi phí khởi tạo framework và ứng dụng |
| Container readiness | Từ khi container được khởi chạy đến khi health/readiness thành công | Đánh giá khả năng nhận traffic |
| Cold request latency | Từ khi client gửi request kích hoạt instance mới đến khi nhận response hoàn chỉnh | Đo trải nghiệm người dùng khi phải chờ scale from zero |
| Warm request latency | Độ trễ request khi instance đã sẵn sàng và xử lý ổn định | Đánh giá hiệu năng xử lý nghiệp vụ |
| Time to stable throughput | Thời gian từ khi bắt đầu đến khi đạt tốc độ xử lý ổn định dưới tải | Hữu ích khi đánh giá JVM JIT warmup và độ ổn định |

Các thước đo này không tương đương. Cold request latency có thể bao gồm lập lịch, lấy image, khởi tạo container, routing, TLS và thời gian xử lý request. Application startup được đo trong process không nhìn thấy toàn bộ khoảng thời gian đó.

Khi so sánh trên Cloud Run, hãy báo cáo ít nhất hai đại lượng: thời gian ứng dụng sẵn sàng và latency của request đầu tiên. Đồng thời kiểm tra tỷ lệ request thực sự gặp cold start; nếu phần lớn traffic đi vào instance ấm, cải thiện startup có thể ít ảnh hưởng đến p95 latency tổng thể.

## 8. Ghi dấu thời điểm ứng dụng Spring sẵn sàng

Ứng dụng có thể tự ghi lại thời gian kể từ lúc hàm main bắt đầu đến sự kiện ApplicationReadyEvent:

~~~java
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class OrdersApplication {
  private static final Logger log =
      LoggerFactory.getLogger(OrdersApplication.class);

  public static void main(String[] args) {
    final long begin = System.nanoTime();
    SpringApplication app = new SpringApplication(OrdersApplication.class);
    app.addListeners((ApplicationListener<ApplicationReadyEvent>) event ->
        log.info("app_ready_ms={}",
            TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - begin)));
    app.run(args);
  }
}
~~~

Sử dụng System.nanoTime để đo khoảng thời gian, không trừ hai timestamp tường. Giá trị app_ready_ms giúp so sánh phần khởi động từ hàm main đến ApplicationReadyEvent. Nó không bao gồm thời gian hệ điều hành tạo process, image pull hay mọi giai đoạn trước hàm main; cần kết hợp với telemetry ở tầng container.

Nếu cần định nghĩa readiness riêng cho dịch vụ, Spring Boot Actuator có thể cung cấp health probes:

~~~properties
server.port=${PORT:8080}
management.endpoint.health.probes.enabled=true
~~~

Trong Cloud Run, container phải lắng nghe trên cổng được nền tảng chỉ định qua biến môi trường PORT. Cấu hình cổng thực tế cần đọc giá trị PORT tại runtime; dùng 8080 chỉ phù hợp khi service được cấu hình chạy ở cổng đó. Không để health endpoint đưa ra tín hiệu "ready" trước khi những thành phần bắt buộc cho việc phục vụ request thực sự sẵn sàng.

Readiness không nên phụ thuộc cứng vào mọi dịch vụ ngoài nếu lỗi tạm thời của dependency khiến toàn bộ instance bị loại khỏi lưu lượng không cần thiết. Hãy định nghĩa theo việc ứng dụng có thể phục vụ đúng chức năng quan trọng và theo mô hình chịu lỗi đã thiết kế.

## 9. Triển khai hai biến thể trên Cloud Run

Để so sánh, có thể tạo hai Cloud Run services độc lập với cấu hình giống nhau, một chạy image JVM và một chạy image native. Ví dụ:

~~~bash
gcloud run deploy orders-jvm \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-jvm:trial \
  --cpu=1 --memory=1Gi \
  --concurrency=20 \
  --min-instances=0 --max-instances=5 \
  --no-allow-unauthenticated
~~~

~~~bash
gcloud run deploy orders-native \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-native:trial \
  --cpu=1 --memory=1Gi \
  --concurrency=20 \
  --min-instances=0 --max-instances=5 \
  --no-allow-unauthenticated
~~~

Hai service phải có cùng region, giới hạn CPU/RAM, concurrency, autoscaling, cấu hình mạng và các dependency. Nếu muốn đo riêng lợi ích giảm RAM, sau vòng so sánh công bằng có thể chạy vòng thứ hai với memory allocation phù hợp cho từng biến thể; không đổi CPU hoặc RAM giữa hai nhánh trong cùng phép đo startup ban đầu.

Cloud Run có cấu hình startup CPU boost và minimum instances. Hai yếu tố này ảnh hưởng startup/cold start nên phải giữ cùng trạng thái trong cặp so sánh và ghi lại trong kết quả. Minimum instances lớn hơn 0 có thể giảm tỷ lệ cold start nhưng tạo chi phí duy trì; nó không làm bản thân ứng dụng khởi động nhanh hơn.

Khi service yêu cầu xác thực, công cụ benchmark phải có danh tính hợp lệ và gửi identity token thích hợp. Không chuyển service thành public chỉ để chạy bài đo nếu môi trường thử nghiệm không cho phép. Hãy dùng project và tài nguyên thử nghiệm được phép.

## 10. Thiết kế thí nghiệm startup có thể lặp lại

Một lần khởi động nhanh không đủ để kết luận. Native và JVM có thể bị ảnh hưởng bởi cache của image, vị trí instance, tốc độ mạng, độ trễ database, mức tải và đặc điểm bản build. Nên thực hiện nhiều lượt đo trong các điều kiện tương đương:

1. **Cố định phiên bản:** dùng cùng commit, dependency, cấu hình feature flag và dữ liệu kiểm thử. Ghi lại phiên bản Java, GraalVM, Spring Boot và image digest.
2. **Cố định hạ tầng:** cùng region, CPU, memory, concurrency, request timeout, min/max instances, startup boost và endpoint.
3. **Cố định dependency:** cùng database, mạng, cache và quyền IAM. Phân biệt startup nội tại của app với thời gian chờ dịch vụ ngoài.
4. **Định nghĩa rõ cold start:** theo dõi log tạo instance và log sẵn sàng; không mặc định rằng chỉ gửi request sau một quãng chờ đã chắc chắn tạo instance mới.
5. **Lặp lại nhiều lượt:** đo các lần khởi động thực sự của instance mới, thay đổi thứ tự JVM/native để giảm thiên lệch do thời điểm và tải nền.
6. **Đo riêng warm traffic:** cho ứng dụng đạt trạng thái ổn định rồi chạy cùng mô hình lưu lượng, payload và thời lượng.
7. **Lưu telemetry:** lấy Cloud Logging, Cloud Monitoring và dữ liệu từ load generator; ghi rõ những lần thử lỗi và nguyên nhân.
8. **Tổng hợp thống kê:** báo cáo median/p50, p95, p99 khi số mẫu đủ lớn, độ phân tán, số mẫu và điều kiện thử.

Scale-to-zero với min instances bằng 0 không bảo đảm rằng mỗi request sau một khoảng chờ tùy ý là cold request. Nền tảng có thể giữ instance trong một thời gian sau khi ngừng traffic. Có thể dùng các revision hoặc đợt triển khai mới để tạo cơ hội quan sát startup, đồng thời xác nhận bằng log/metric rằng instance mới đã được tạo.

Không chạy phép đo duy nhất trên máy phát triển rồi lấy kết quả làm cold start Cloud Run. Khởi động local giúp phát hiện regression trong ứng dụng, nhưng không bao quát ảnh hưởng của nền tảng và đường mạng.

## 11. Bảng ghi kết quả benchmark

Mẫu bảng dưới đây nên được điền bằng số liệu từ lần thử nghiệm của nhóm. Không suy ra kết quả chỉ từ tên công nghệ.

| Metric | JVM | Native Image | Cách diễn giải |
| --- | --- | --- | --- |
| Application startup p50/p95 | Cần đo | Cần đo | Thời gian từ main đến ApplicationReadyEvent |
| Container readiness p50/p95 | Cần đo | Cần đo | Khi instance có thể nhận traffic |
| Cold request latency p50/p95 | Cần đo | Cần đo | Bao gồm độ trễ từ góc nhìn client |
| Warm request latency p50/p95 | Cần đo | Cần đo | Kiểm tra đánh đổi với throughput/latency |
| Resident memory hoặc container memory | Cần đo | Cần đo | So sánh trong cùng mô hình tải |
| CPU khi idle và khi tải | Cần đo | Cần đo | Phát hiện khác biệt tiêu thụ tài nguyên |
| Throughput tại cùng latency target | Cần đo | Cần đo | Xem khả năng xử lý traffic |
| Thời gian build và RAM build | Cần đo | Cần đo | Chi phí CI và tốc độ phát hành |
| Image size và thời gian pull | Cần đo | Cần đo | Ảnh hưởng đến phân phối artifact |
| Lỗi, timeout và retry | Cần đo | Cần đo | Không đánh đổi độ tin cậy lấy startup |
| Ước lượng chi phí theo workload | Cần tính | Cần tính | Cân nhắc CPU/RAM và tần suất khởi tạo |

Khi báo cáo, ghi cả đơn vị, số lần thử, cấu hình service, commit, image digest và cách sinh request. Ví dụ "native nhanh hơn 3 lần" không đủ rõ nếu không biết nhanh hơn về application startup, cold request p95 hay thời gian build.

Một mô hình ước lượng tác động startup tới trải nghiệm là:

\[
\text{Latency trung bình} \approx
p_{\text{cold}} \times L_{\text{cold}}
+ (1-p_{\text{cold}}) \times L_{\text{warm}}
\]

Trong đó p_cold là tỷ lệ request gặp cold start, còn L_cold và L_warm là latency trung bình tương ứng. Đây là phép ước lượng đơn giản, chưa thể hiện phân phối đuôi p95/p99 hoặc các request đồng thời chờ một instance mới. Với SLO latency, hãy dùng phân phối thực tế thay cho chỉ số trung bình.

## 12. GKE: startup liên quan đến readiness và autoscaling

Trên GKE, ứng dụng native và JVM đều chạy trong pod. Startup cần được xem cùng quá trình scheduler gán pod lên node, pull image, container start, startup probe, readiness probe và rollout. Nếu deployment dùng Horizontal Pod Autoscaler, thời gian từ lúc tạo pod đến lúc pod nhận traffic ảnh hưởng khả năng đáp ứng đột biến tải.

Với Spring Boot Actuator, một ví dụ cấu hình probe trong Kubernetes:

~~~yaml
containers:
  - name: orders-api
    image: asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-native:trial
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 5
      failureThreshold: 24
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      failureThreshold: 3
~~~

Đây là phần containers của PodSpec, không phải manifest Deployment đầy đủ. Các ngưỡng chỉ là ví dụ; hãy điều chỉnh theo startup thực tế và hành vi ứng dụng. Startup probe cho phép ứng dụng có thời gian khởi động trước khi các kiểm tra sống/khả dụng khác can thiệp; readiness quyết định khi nào pod được đưa vào tập endpoint phục vụ.

Với GKE, nên đo cả pod startup và ready-to-serve, không chỉ Spring startup. Nếu image pull hoặc chờ node mới chiếm phần lớn thời gian scale out, cải thiện thời gian khởi động của executable có thể không phải nút thắt chính. Hãy đối chiếu HPA, node autoscaling, pod scheduling và hiệu năng ứng dụng trong cùng một lần thử.

## 13. Memory, throughput, chi phí và vận hành

Native Image thường giảm phần overhead của JVM runtime và có thể phù hợp với instance có bộ nhớ nhỏ. Tuy vậy, kết luận phải dựa trên memory thực tế khi tải, không chỉ heap size. Với JVM, cần phân biệt heap, non-heap và container RSS; với native cũng cần xem resident memory, native allocations và memory peak khi xử lý request.

Khi đánh giá chi phí trên Google Cloud, hãy tính đến:

- Số instance được tạo hoặc duy trì và tần suất cold start.
- CPU và memory allocation của Cloud Run hoặc requests/limits trong GKE.
- Thời gian xử lý request nóng và hiệu suất khi tăng concurrency.
- CPU/RAM cần cho native compilation trên CI, thời gian build và thời gian chờ release.
- Kích thước image, lưu trữ Artifact Registry và lưu lượng phân phối image.
- Chi phí duy trì min instances, node capacity và hệ thống quan sát.

Ví dụ, nếu native giảm startup đáng kể nhưng throughput dưới tải giảm, hệ thống có thể cần thêm instance để phục vụ cùng lưu lượng. Trong trường hợp đó, chi phí chạy có thể không giảm tương ứng với mức giảm RAM của từng instance.

Ngược lại, nếu workload thường scale từ 0 và xử lý request ngắn, một native image có startup nhanh và memory allocation thấp có thể giảm cold request latency và cải thiện chi phí. Hãy thử cả cấu hình mặc định và cấu hình tối ưu riêng cho từng biến thể sau khi đã có phép so sánh cùng tài nguyên.

## 14. Tác động đến CI/CD và chuỗi cung ứng phần mềm

Native compilation thường dài và tiêu tốn tài nguyên hơn build JAR. Vì vậy, pipeline cần tách các mức kiểm tra hợp lý: compile/test JVM nhanh ở mỗi pull request; native build và test quan trọng ở nhánh release hoặc trên lịch phù hợp; canary trước khi chuyển toàn bộ traffic.

Một pipeline phát hành có thể gồm:

1. Kiểm thử đơn vị và tích hợp trên JVM.
2. Chạy AOT/native build trong môi trường CI đủ tài nguyên.
3. Chạy native smoke tests và kiểm thử các đường đi có reflection/resource.
4. Đẩy image vào Artifact Registry với tag bất biến hoặc digest.
5. Triển khai revision Cloud Run hoặc GKE canary.
6. Theo dõi readiness, cold request latency, lỗi, memory và throughput.
7. Phát hành tiếp hoặc rollback theo SLO và error budget.

Builder, buildpack, JDK, GraalVM và dependency cần được ghi nhận phiên bản để tránh khó tái hiện. Sử dụng service account CI có quyền tối thiểu, bảo vệ secrets và đánh giá provenance của artifact. Cần chuẩn bị rollback về phiên bản JVM hoặc native đã chạy ổn định nếu bản build native mới gặp lỗi chỉ xuất hiện trong production.

Không nên bỏ qua bảo mật dependency hoặc cập nhật bản vá chỉ vì rebuild native tốn thời gian. Với native artifact, việc nâng cấp thư viện hoặc runtime liên quan có thể yêu cầu build lại executable và chạy lại các kiểm thử tương thích.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Native compile lỗi hết RAM hoặc mất nhiều thời gian | Builder thiếu tài nguyên hoặc dependency phức tạp | Kiểm tra log Native Image, RAM/CPU builder và cache build |
| Executable không khởi động trong container | Sai OS/architecture hoặc thiếu thư viện runtime | Kiểm tra platform của builder và image chạy trên GCP |
| Endpoint chạy trên JVM nhưng lỗi native | Reflection, proxy, resource, JNI hoặc code path động | Kiểm tra stack trace, runtime hints và test native cụ thể |
| Cloud Run báo container không lắng nghe đúng cổng | App cấu hình cổng khác PORT hoặc khởi động lỗi | Kiểm tra log startup, port và container contract |
| Startup app tốt nhưng cold request vẫn chậm | Image pull, scheduling, network hoặc dependency chậm | Đo tách các giai đoạn và quan sát tầng Cloud Run/GKE |
| Native startup tốt nhưng warm latency xấu hơn | Đặc điểm workload, tối ưu biên dịch hoặc JIT trên JVM | Benchmark tải ổn định và phân tích CPU/throughput |
| Kết quả mỗi lần đo khác nhiều | Cold/warm trộn lẫn, cache, autoscaling và tải nền | Xác thực instance mới, lặp nhiều lượt, báo cáo phân phối |
| Health check thành công quá sớm | Readiness chưa phản ánh khả năng phục vụ thật | Định nghĩa readiness theo chức năng bắt buộc |
| Image native có secret hoặc cấu hình cứng | Nhầm dữ liệu build time và runtime | Truyền cấu hình nhạy cảm qua Secret Manager/runtime environment |

## 16. Bài thực hành và tiêu chí quyết định

**Tình huống:** một Spring Boot API xử lý đơn hàng đang chạy trên Cloud Run, min instances bằng 0. Người dùng phản ánh request đầu tiên sau khoảng thời gian ít traffic có latency cao. Nhóm muốn biết có nên chuyển sang GraalVM Native Image hay giữ JVM và tối ưu cách khởi động.

Hãy thực hiện:

1. Ghi commit, phiên bản Spring Boot/Java và cấu hình baseline hiện tại.
2. Build hai image JVM/native từ cùng source, không đổi logic nghiệp vụ.
3. Deploy thành hai service thử nghiệm với cùng CPU, memory, concurrency, region và startup boost.
4. Ghi app_ready_ms, thời gian sẵn sàng container, request đầu tiên và warm request latency.
5. Thực hiện đủ số lần khởi động mới để có p50/p95 có ý nghĩa; đối chiếu log để chắc chắn phép đo là cold start.
6. Chạy cùng kịch bản tải, thu memory, CPU, throughput, tỷ lệ lỗi và thời gian build.
7. Xem yếu tố chi phối latency: JVM startup, chờ database, image pull hay scheduling.
8. Đề xuất một quyết định: tiếp tục JVM với cấu hình tối ưu; thử native canary; hoặc dùng native production với điều kiện chấp nhận và rollback rõ ràng.

Một kết luận tốt phải trả lời được: người dùng được lợi bao nhiêu ở p95/p99, bao nhiêu request thực sự chịu cold start, memory/cost thay đổi ra sao, có regression ở warm traffic không, và thời gian CI có phù hợp nhịp phát hành không. Nếu startup bị chi phối bởi dependency từ xa, nên tối ưu dependency hoặc lazy initialization hợp lý trước khi kết luận phải đổi runtime.

## 17. Checklist trước khi chọn Native Image trên GCP

- Đã có SLI/SLO hoặc mục tiêu latency liên quan startup và cold request.
- Đã phân biệt application startup, container readiness và end-to-end cold request latency.
- Ứng dụng Spring Boot và dependency hỗ trợ AOT/native theo phiên bản đang dùng.
- Reflection, resource, serialization, proxy và code path ít dùng được kiểm thử trên native.
- Build native được thực hiện cho đúng OS/architecture và có đủ tài nguyên CI.
- Hai biến thể được thử với cùng mã nguồn, CPU/RAM, region, concurrency và cấu hình scaling.
- Đã đo lặp nhiều lần, phân biệt instance mới và instance ấm, lưu số mẫu cùng phân phối độ trễ.
- Đã so sánh memory, warm throughput, tỷ lệ lỗi, thời gian build và chi phí tổng thể.
- Cloud Run hoặc GKE có readiness/startup probes hợp lý và logging đủ để điều tra.
- Pipeline ghi lại image digest, builder/runtime version, có native tests, canary và rollback.
- Quyết định được ghi kèm điều kiện chấp nhận thay đổi và kế hoạch quan sát sau phát hành.

GraalVM Native Image là một công cụ tối ưu đáng giá khi startup và footprint thật sự ảnh hưởng trải nghiệm hoặc chi phí. Trên Google Cloud, lựa chọn đúng cần kết hợp đặc điểm Java/Spring với hoạt động scale và phân phối traffic của Cloud Run hoặc GKE. Khi đo đúng các lớp latency, kiểm tra tính tương thích và so sánh hiệu năng nóng cùng chi phí build, nhóm có thể chọn native hay JVM dựa trên bằng chứng thay vì suy đoán.
