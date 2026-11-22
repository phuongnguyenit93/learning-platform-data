# Giới hạn bộ đệm và vòng đời dữ liệu đo trong Spring Boot

## 1. Mục tiêu của bài học

Spring Boot có cơ chế ApplicationStartup để quan sát các bước SpringApplication và ApplicationContext thực hiện khi khởi động. Mỗi bước được biểu diễn bằng StartupStep và có thể có tên, mã định danh, quan hệ cha–con, nhãn (tags) và thời gian thực thi. Một implementation hữu ích là BufferingApplicationStartup: giữ các step đã hoàn tất trong bộ nhớ để xem trực tiếp hoặc xuất qua Actuator.

Tuy nhiên dữ liệu này có vòng đời hữu hạn. Không chỉ cần bật đo, người vận hành còn phải trả lời:

- Bộ đệm chứa bao nhiêu bản ghi, và đơn vị giới hạn là gì?
- Khi đầy, step mới bị bỏ qua hay ghi đè step cũ?
- Khi lấy snapshot bằng GET, dữ liệu có bị xóa không?
- Khi gọi POST/drain, dữ liệu còn ở đâu?
- Sau khi JVM restart, liệu có thể lấy lại timeline cũ?
- Một step không xuất hiện có thật sự chứng minh nó chưa từng chạy không?

**Quy tắc chính:** BufferingApplicationStartup dùng capacity tính theo **số startup step event được lưu**, không phải byte, mili-giây hay kích cỡ file. Khi bộ đệm đầy, những step mới không được ghi lại; nó **không phải ring buffer** tự loại step cũ. Snapshot chỉ đọc, còn drain trả dữ liệu và xóa event khỏi bộ đệm. Không có lưu trữ bền vững tự động.

Bài sử dụng **Spring Boot 3.3.13, Spring Framework 6.1.x, Java 17+** làm hệ quy chiếu để tránh lẫn hành vi giữa các phiên bản.

## 2. Các thành phần đo startup

| API hoặc thành phần | Vai trò |
| --- | --- |
| ApplicationStartup | Giao diện tạo StartupStep bằng start(name) |
| StartupStep | Một bước được instrument; có tên, ID, parentId, tags và end() |
| BufferingApplicationStartup | Implementation giữ một số lượng step có giới hạn trong RAM |
| StartupTimeline | Tập TimelineEvent cùng thời điểm bắt đầu timeline |
| StartupTimeline.TimelineEvent | Start time, end time, duration và StartupStep liên quan |
| getBufferedTimeline() | Lấy snapshot mà không tiêu thụ buffer |
| drainBufferedTimeline() | Lấy và loại các event đang được buffer |
| addFilter(Predicate) | Chỉ giữ step thỏa các filter |
| Actuator startup endpoint | Xuất timeline dưới dạng JSON bằng GET hoặc POST |
| FlightRecorderApplicationStartup | Đưa startup steps vào Java Flight Recorder, cơ chế khác |
| Micrometer startup timers | application.started.time và application.ready.time: số đo tổng hợp |

Spring Boot không tự instrument mọi dòng Java và mọi thư viện. ApplicationStartup thu thập những bước mà Spring Framework, Spring Boot hoặc code có chủ đích ghi bằng API này. Một công việc chạy mà không có StartupStep không đương nhiên xuất hiện trong timeline.

### Bắt đầu và kết thúc một bước

~~~java
StartupStep step = recorder.start("demo.load-cache");
try {
    warmUpCache();
} finally {
    step.end();
}
~~~

Đây là đoạn minh họa trong method, cần import org.springframework.core.metrics.StartupStep và định nghĩa warmUpCache(). Đặt end() trong finally giúp recorder biết bước đã hoàn tất cả khi code ném exception. Tùy cách ghi, event hoàn chỉnh chỉ có thể được tạo khi step được end(); start(name) đơn lẻ chưa bảo đảm timeline có endTime hoặc duration.

Một StartupStep có thể gắn tag:

~~~java
StartupStep step = recorder.start("demo.load");
step.tag("component", "pricing");
try {
    initializePricing();
} finally {
    step.end();
}
~~~

Đây cũng là mã minh họa cần service initializePricing() thật. Chỉ gắn metadata không nhạy cảm; tránh token, mật khẩu, dữ liệu khách hàng trong tags.

## 3. Capacity là giới hạn đếm event, không phải dung lượng byte

Khởi tạo recorder:

~~~java
BufferingApplicationStartup recorder =
        new BufferingApplicationStartup(2048);
~~~

Tham số 2048 nghĩa là số event mong muốn giữ trong buffer theo cấu hình. Đây chỉ là giá trị ví dụ trong tài liệu Spring Boot, **không phải capacity mặc định của mọi ứng dụng**. SpringApplication sẽ không tự tạo BufferingApplicationStartup(2048) chỉ vì có Actuator.

Giả sử capacity bằng 3:

~~~text
Step A ket thuc -> ghi vao buffer: [A]
Step B ket thuc -> ghi vao buffer: [A, B]
Step C ket thuc -> ghi vao buffer: [A, B, C]
Step D ket thuc -> buffer day, khong ghi
Step E ket thuc -> buffer day, khong ghi
Snapshot         -> [A, B, C]
~~~

Nếu một cấu trúc được thiết kế như ring buffer, nó có thể lưu C, D, E. Nhưng **BufferingApplicationStartup không dùng chính sách thay thế như vậy**. Sau khi đầy, những step mới bị bỏ qua cho tới khi buffer có chỗ. Trong luồng song song, thứ tự kết thúc có thể khác thứ tự bắt đầu, vì vậy không được đồng nhất “đầu tiên trong buffer” với “method bắt đầu sớm nhất”.

### Tác động khi buffer đầy

- Ứng dụng có thể khởi động và đạt ReadinessState.ACCEPTING_TRAFFIC bình thường.
- Dữ liệu quan sát bị thiếu, thường khiến các bước ở giai đoạn muộn không có trong timeline.
- Không có nghĩa Spring đã bỏ qua việc tạo bean hoặc chạy runner.
- Không bảo đảm parentId trong một event còn một event cha tương ứng nếu một phần timeline đã mất.
- Không có phép tính nào khôi phục được một step chưa từng được ghi vào buffer.
- Một response đúng bằng capacity event là dấu hiệu cần kiểm tra, **không phải bằng chứng tuyệt đối** rằng đã có overflow.

Capacity là giới hạn **số lượng**, không phải RAM tối đa. Event lưu thời điểm, chuỗi tên, tags và cấu trúc object nên lượng heap phụ thuộc nội dung và JVM; không thể khẳng định 2048 event luôn chiếm một số MB cố định.

## 4. Vòng đời dữ liệu từ lúc tạo recorder đến khi process kết thúc

~~~text
Tao BufferingApplicationStartup(capacity)
                 |
                 v
Recorder bat dau ghi
                 |
SpringApplication.setApplicationStartup(recorder)
                 |
SpringApplication.run(args)
                 |
Spring Framework / Boot tao cac StartupStep
                 |
StartupStep.end()
                 |
  +-- filter khong khop -> khong ghi
  +-- buffer con cho   -> ghi TimelineEvent
  +-- buffer day       -> bo qua event moi
                 |
                 v
JVM tiep tuc chay
  |
  +-- getBufferedTimeline() -> snapshot, buffer giu nguyen
  |
  +-- drainBufferedTimeline() -> tra event, buffer bo event
  |
  +-- co them step sau drain -> co the ghi them neu con cho
  |
  +-- JVM thoat / restart -> RAM cua recorder cu mat
~~~

**Ba mốc cần nhớ:**

1. **Trước SpringApplication.run:** phải đăng ký ApplicationStartup để thu các bước khởi động ban đầu. Tạo recorder quá muộn không ghi lại lịch sử đã qua.
2. **Sau khi app Ready:** buffer vẫn có thể còn sống trong cùng JVM, cho GET/POST hoặc Java API truy cập. Nếu có bước được instrument sau Ready, nó cũng có thể xuất hiện, nhưng đây không phải một lần khởi động mới.
3. **Sau process exit/restart:** dữ liệu RAM của recorder cũ không còn. Chỉ file JSON, collector hoặc recording đã xuất ra kho bền vững mới bảo toàn lịch sử.

Đối với nhiều Pod/replica, mỗi JVM có recorder riêng. Nếu muốn so sánh rollout, cần lưu kèm instance ID, build version, profile, thời điểm bắt đầu và cấu hình tương ứng của từng instance.

## 5. API đọc/xả và ý nghĩa lưu trữ

### getBufferedTimeline(): snapshot

~~~java
StartupTimeline current = recorder.getBufferedTimeline();
int count = current.getEvents().size();
~~~

Đây là mã minh họa với recorder có sẵn, cần import StartupTimeline. Method trả snapshot các event đã ghi **không xóa chúng** khỏi recorder. Gọi nhiều lần mà không có step mới/drain thường cho cùng số lượng event.

Snapshot là một object riêng giữ danh sách event. Nếu code tiếp tục giữ tham chiếu, bộ nhớ vẫn có thể bị chiếm dù recorder sau đó được drain.

### drainBufferedTimeline(): lấy và loại event

~~~java
StartupTimeline captured = recorder.drainBufferedTimeline();
int count = captured.getEvents().size();
~~~

Method trả về những event hiện có và loại chúng khỏi bộ đệm. Nếu sau đó gọi getBufferedTimeline() và không có step mới, số lượng event sẽ là 0. Event trong object captured vẫn tồn tại nếu caller còn giữ tham chiếu; drain **không đồng nghĩa GC sẽ thu hồi RAM ngay lập tức**.

Sau drain, recorder có thể lưu step mới trong khả năng capacity còn lại, nhưng các step bị bỏ qua khi buffer đã đầy **không tự được replay**.

### startRecording(): không phải một nút reset tùy ý

Constructor BufferingApplicationStartup bắt đầu recording. API startRecording() chỉ hợp lệ trong các điều kiện nhất định; Javadoc Spring Boot 3.3 ghi rõ nó có thể ném IllegalStateException nếu đã có step được buffer. Không dùng nó như lệnh đo lại toàn bộ một ApplicationContext đã khởi động, vì việc gọi method không tự tạo lại bean hoặc refresh context.

### addFilter(): giảm lượng event giữ trong bộ đệm

~~~java
recorder.addFilter(step ->
        step.getName().startsWith("spring.beans."));
~~~

Các filter mới được kết hợp với filter đang có theo **AND**. Nếu thêm hai điều kiện tên có prefix loại trừ nhau, có thể không có step nào được giữ. Nếu cần OR, biểu diễn OR trong cùng predicate:

~~~java
recorder.addFilter(step ->
        step.getName().startsWith("spring.beans.")
        || step.getName().startsWith("spring.context."));
~~~

Chỉ nên thêm filter **trước khi run** để quy tắc ghi nhất quán. Filter không xóa event đã ghi từ trước và không khôi phục event đã bị loại. Nếu filter chỉ lấy các bước tạo bean, bạn có thể bỏ sót nguyên nhân chậm ở scanning, class loading, cấu hình hoặc những giai đoạn khác. Cần chọn filter dựa trên câu hỏi đo lường.


## 6. Ví dụ Java 17 kiểm chứng capacity, snapshot, drain và filter

Ví dụ tự tạo step tuần tự để kết quả xác định, không phụ thuộc một ứng dụng thật có bao nhiêu bean. Đặt tệp **src/main/java/demo/BufferCapacityProof.java** trong project Gradle ở mục tiếp theo:

~~~java
package demo;

import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.core.metrics.StartupStep;

public class BufferCapacityProof {

    public static void main(String[] args) {
        BufferingApplicationStartup recorder =
                new BufferingApplicationStartup(3);

        for (int i = 1; i <= 5; i++) {
            StartupStep step = recorder.start("demo.step." + i);
            step.end();
        }

        System.out.println("SNAPSHOT_ONE="
                + recorder.getBufferedTimeline().getEvents().size());
        System.out.println("SNAPSHOT_TWO="
                + recorder.getBufferedTimeline().getEvents().size());

        System.out.println("DRAINED="
                + recorder.drainBufferedTimeline().getEvents().size());
        System.out.println("AFTER_DRAIN="
                + recorder.getBufferedTimeline().getEvents().size());

        recorder.start("demo.after-drain").end();
        System.out.println("NEW_EVENT="
                + recorder.getBufferedTimeline().getEvents().size());

        BufferingApplicationStartup filtered =
                new BufferingApplicationStartup(3);
        filtered.addFilter(
                step -> step.getName().startsWith("demo.keep."));

        filtered.start("demo.skip.one").end();
        filtered.start("demo.keep.one").end();
        filtered.start("demo.skip.two").end();
        filtered.start("demo.keep.two").end();

        System.out.println("FILTERED="
                + filtered.getBufferedTimeline().getEvents().size());
    }
}
~~~

Với Spring Boot 3.3.13 và những step được kết thúc tuần tự, các dòng do chương trình in:

~~~text
SNAPSHOT_ONE=3
SNAPSHOT_TWO=3
DRAINED=3
AFTER_DRAIN=0
NEW_EVENT=1
FILTERED=2
~~~

Giải thích từng dòng:

- SNAPSHOT_ONE=3: năm bước kết thúc, chỉ ba bước có chỗ trong buffer.
- SNAPSHOT_TWO=3: snapshot thứ hai không tiêu thụ dữ liệu.
- DRAINED=3: drain trả đúng ba event đang có.
- AFTER_DRAIN=0: recorder không còn những event vừa được lấy.
- NEW_EVENT=1: recorder tiếp tục nhận step sau drain; không khôi phục những bước thứ tư và thứ năm đã bị bỏ qua.
- FILTERED=2: chỉ hai step có tên demo.keep. khớp predicate.

**Tính xác định:** đây là ví dụ tuần tự, không có nhiều thread tranh chấp buffer hoặc kết thúc step ngoài thứ tự. Với startup thực tế, không assert rằng một ứng dụng luôn sinh chính xác một số step cố định giữa các phiên bản.

## 7. Project Spring Boot 3.3/Java 17 có Actuator startup endpoint

Ta tạo web application hoàn chỉnh để xem những event **thực tế của Spring Boot startup**, rồi thực hiện GET và POST. Dùng Gradle, Java 17 và Spring Boot 3.3.13.

### Cấu trúc thư mục

~~~text
startup-buffer-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          StartupBufferDemo.java
          BufferCapacityProof.java
      resources/
        application.properties
~~~

### Tệp settings.gradle

~~~groovy
rootProject.name = 'startup-buffer-demo'
~~~

### Tệp build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.register('bufferProof', JavaExec) {
    group = 'verification'
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.BufferCapacityProof'
}
~~~

Task bufferProof chỉ chạy ví dụ API độc lập ở mục 6; bootRun chạy Spring Boot web application. Cần JDK 17+, Gradle tương thích và các dependency đã có trong cache hoặc được phép tải từ repository.

### Tệp application.properties

~~~properties
spring.application.name=startup-buffer-demo
server.port=8080
management.endpoints.web.exposure.include=health,info,startup
~~~

Startup endpoint **không nằm trong tập web exposure mặc định**, vì vậy phải thêm startup vào danh sách. Cấu hình này dành cho môi trường thực hành có kiểm soát; không expose endpoint công khai khi chưa có authentication, authorization và network policy thích hợp.

### Tệp StartupBufferDemo.java

~~~java
package demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class StartupBufferDemo {

    public static void main(String[] args) {
        BufferingApplicationStartup startup =
                new BufferingApplicationStartup(2048);

        SpringApplication app =
                new SpringApplication(StartupBufferDemo.class);
        app.setApplicationStartup(startup);
        app.run(args);

        boolean recorded = !startup.getBufferedTimeline()
                .getEvents().isEmpty();
        System.out.println("BUFFER_NONEMPTY=" + recorded);
    }

    @Bean
    ApplicationRunner startupRunner() {
        return args -> System.out.println("RUNNER_COMPLETED");
    }
}
~~~

Các điểm then chốt:

1. SpringApplication được tạo riêng, không dùng static run trước khi có recorder.
2. **setApplicationStartup(startup) chạy trước app.run(args)** nên Spring/Boot có thể ghi nhận startup steps ngay từ đầu những giai đoạn được instrument.
3. 2048 là capacity ví dụ, không phải một giá trị bắt buộc.
4. getBufferedTimeline() trong main chỉ snapshot, không drain, nhờ đó dữ liệu vẫn còn cho Actuator.
5. @Bean ApplicationRunner được gọi trước khi SpringApplication.run hoàn tất; code runner không tự tạo StartupStep riêng.
6. Embedded Tomcat chạy lâu để bạn dùng curl.
7. Không tạo thêm một @Bean BufferingApplicationStartup khác: Spring Boot đã nhận instance qua SpringApplication và sẽ dùng nó cho startup instrumentation.

### Chạy thử

Nếu project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có Gradle wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle bootRun
~~~

Các dòng riêng do ví dụ tự in, theo thứ tự:

~~~text
RUNNER_COMPLETED
BUFFER_NONEMPTY=true
~~~

Các log Spring Boot, Tomcat hoặc Gradle có thể xen giữa. Đừng assert số event cụ thể của app: số lượng tùy auto-configuration, profile, classpath, phiên bản framework và filters.

Chạy phần thử sức chứa riêng:

~~~bash
./gradlew -q bufferProof
~~~

Các dòng output dự kiến chính là sáu dòng ở cuối mục 6. Chương trình này không mở web server.

## 8. GET /actuator/startup là snapshot

Sau khi bootRun thành công:

~~~bash
curl -i -X GET http://localhost:8080/actuator/startup
~~~

Spring Boot 3.3 Actuator trả JSON với cấu trúc đại ý:

~~~json
{
  "springBootVersion": "3.3.13",
  "timeline": {
    "startTime": "2025-06-19T07:16:19.477Z",
    "events": [
      {
        "startTime": "2025-06-19T07:16:19.805Z",
        "endTime": "2025-06-19T07:16:19.810Z",
        "duration": "PT0.005S",
        "startupStep": {
          "id": 1,
          "name": "spring.beans.instantiate",
          "tags": [
            {
              "key": "beanName",
              "value": "exampleBean"
            }
          ]
        }
      }
    ]
  }
}
~~~

Đây là **JSON minh họa**, không phải output nguyên văn bắt buộc. ID, parentId, timestamps, step names, tags, thứ tự và số event phụ thuộc runtime. Duration ở định dạng ISO-8601, ví dụ PT0.005S là 5 mili-giây.

Gọi GET lần nữa:

~~~bash
curl -s -X GET http://localhost:8080/actuator/startup
~~~

Các event đã có **vẫn được lưu** nếu không có thao tác drain khác. Không suy luận rằng GET đã giải phóng heap.

## 9. POST /actuator/startup là drain

Gửi:

~~~bash
curl -i -X POST http://localhost:8080/actuator/startup
~~~

Theo tài liệu REST API Spring Boot 3.3, POST trả timeline **và xả** những event đã lấy khỏi bộ đệm.

Ngay sau đó, thử lại:

~~~bash
curl -s -X GET http://localhost:8080/actuator/startup
~~~

Khi không có step mới phát sinh sau drain, phần quan trọng là:

~~~json
{
  "timeline": {
    "events": []
  }
}
~~~

Đây là **trích cấu trúc rút gọn**, không phải JSON response đầy đủ vì response thật còn springBootVersion và có thể có timeline.startTime.

**GET = snapshot không phá hủy. POST = tiêu thụ dữ liệu.** POST lần thứ hai thường không thể replay những event của lần POST đầu; nếu có event mới, nó chỉ trả phần mới.

Nếu một collector nhận response POST nhưng ghi file/database thất bại, buffer đã bị xả và dữ liệu không tự quay lại. Vì vậy nên GET rồi lưu bản sao có kiểm tra trước khi quyết định drain, hoặc xây một cơ chế export có kiểm soát và quyền sở hữu dữ liệu rõ.

## 10. Xác định capacity cho ứng dụng thật

Không có capacity tốt cho mọi service. Một project có ít bean có thể chỉ cần vài trăm event, trong khi project lớn với nhiều auto-configurations và nhiều module có thể cần nhiều hơn.

Quy trình đề xuất:

1. Dùng một capacity đủ rộng trong staging, chẳng hạn 2048 hoặc cao hơn tùy ứng dụng.
2. Chạy với profile, classpath, feature flags và container gần production.
3. GET snapshot sau startup, đếm timeline.events.
4. Nếu số lượng sát capacity, tăng lên rồi chạy lại để xem có thêm step không.
5. Nếu cần giữ nhiều lượt đo, **xuất ra nơi lưu bền vững** thay vì giữ toàn bộ ở RAM trong nhiều ngày.
6. Khi chỉ nghiên cứu một loại bước, lọc theo name/tags phù hợp để giảm số event.
7. Benchmark overhead của instrumentation, heap, GC và kích cỡ JSON.
8. Dùng metadata build, commit, profile, pod và cold/warm startup để so sánh công bằng.

**Không cộng mọi duration để ra tổng startup time.** Các step có thể lồng nhau, parent-child overlap; cộng tất cả duration sẽ dễ đếm trùng. Dùng quan hệ parentId và timeline để tìm đoạn chậm, rồi đối chiếu thời gian tổng hợp khác.


## 11. Khi nào một bước không xuất hiện?

Một event vắng mặt có thể có nhiều nguyên nhân:

| Hiện tượng | Khả năng | Việc cần kiểm tra |
| --- | --- | --- |
| GET trả events rỗng ngay sau startup | Recorder đặt muộn, filter chặn, chưa instrument | Main và setApplicationStartup trước run |
| GET rỗng sau một POST | Buffer đã bị drain | Lịch sử request của team/collector |
| Event count bằng capacity | Có khả năng đầy | Tăng capacity và đo lại |
| Chỉ thấy bước spring.beans.* | Filter đã chỉ chọn bean | Predicate đã cấu hình |
| Không thấy bean lazy | Bean chưa được khởi tạo trước Ready | Lazy initialization và request đầu |
| Không thấy custom step | Thiếu end(), dùng recorder khác hoặc bị filter | Vòng đời StartupStep, tags, capacity |
| ParentId không tìm thấy parent | Filter/overflow khiến thiếu event cha | Không xem timeline đã lọc là cây đầy đủ |
| Timestamp không theo thứ tự ID | Step kết thúc khác thứ tự bắt đầu | Dựa startTime/endTime/duration |
| Không thấy dữ liệu sau restart | RAM của JVM cũ đã mất | Collector/file trước termination |
| Chỉ thấy vài phase startup | Không phải mọi giai đoạn đều instrument | Danh mục StartupStep mà framework hỗ trợ |

### Tác vụ bất đồng bộ và lazy beans

Nếu một ApplicationRunner chỉ submit một tác vụ async rồi return, ApplicationReadyEvent có thể xuất hiện trước khi tác vụ đó hoàn tất. BufferingApplicationStartup không tự nối các bước của code background nếu chúng không được instrument. Một lazy bean có thể được khởi tạo khi request đầu tiên tới sau Ready; điều đó không giống khởi động lại application. Vì vậy cần ghi rõ bạn đo **startup theo chuẩn Spring** hay đo cả warm-up/background.

### Khi startup thất bại

Nếu bean init, context refresh hoặc runner làm SpringApplication.run thất bại trước khi web server/Actuator sẵn sàng, HTTP GET/POST có thể không dùng được để xuất dữ liệu. Khi yêu cầu là chẩn đoán startup failure rất sớm, xem xét xuất từ code điều phối có kiểm soát, logs hoặc **FlightRecorderApplicationStartup/JFR** thay vì phụ thuộc hoàn toàn vào một endpoint HTTP sau Ready.

## 12. Phân biệt BufferingApplicationStartup với Micrometer metrics

Spring Boot Actuator có các metric tổng hợp:

- **application.started.time**: thời gian để ứng dụng đạt mốc started.
- **application.ready.time**: thời gian để ứng dụng đạt mốc ready.

Chúng khác với StartupTimeline:

| Đặc tính | Startup timeline | Startup time metrics |
| --- | --- | --- |
| Mức chi tiết | Nhiều StartupStep, mỗi bước có duration và tags | Một vài mốc tổng hợp |
| Bộ nhớ | Bounded event buffer trong JVM | Meter registry theo cấu hình |
| API lấy | getBufferedTimeline hoặc GET startup | /actuator/metrics hoặc metrics backend |
| API xả | drainBufferedTimeline hoặc POST startup | Không liên quan POST startup |
| Dùng để | Tìm bước/bean/giai đoạn chậm | Theo dõi xu hướng qua deploy |
| Dữ liệu qua restart | Mất nếu chưa export | Tùy registry và backend có lưu dữ liệu |

POST /actuator/startup **không phải lệnh xóa Micrometer startup timers**. Ngược lại, thấy application.ready.time không chứng minh mọi startup step đã được buffer. Đừng thay một công cụ bằng công cụ kia khi cần chẩn đoán sâu.

## 13. Khi cần JFR thay vì bộ đệm trong RAM

**FlightRecorderApplicationStartup** là implementation của Spring Framework dành cho Java Flight Recorder. Nó hữu ích khi cần liên hệ startup với JVM class loading, allocations, GC, hoạt động thread và các JFR events khác.

Cấu hình minh họa trong main:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new FlightRecorderApplicationStartup());
app.run(args);
~~~

Đây là đoạn trích, cần import:

~~~java
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;
~~~

và MyApplication là class Spring Boot thật.

Ví dụ bật JFR với JVM:

~~~bash
java -XX:StartFlightRecording:filename=recording.jfr,duration=15s -jar app.jar
~~~

JFR có vòng đời, chính sách recording và output file riêng. Không phải một BufferingApplicationStartup có capacity lớn hơn; việc dùng JFR không có nghĩa endpoint /actuator/startup luôn tự cung cấp timeline JSON. Nếu muốn xem GET/POST dữ liệu buffer, dùng BufferingApplicationStartup theo hướng dẫn đã kiểm chứng.

## 14. Bảo mật và quyền sở hữu dữ liệu startup

Startup endpoint chứa metadata có thể tiết lộ bean names, package names, framework components và custom tags. **POST còn làm thay đổi buffer**, nên có thể làm các nhóm quan sát khác mất dữ liệu đang cần.

- Không expose startup ra public Internet nếu chưa có xác thực và phân quyền.
- Chỉ mở endpoint ở management network/namespace phù hợp.
- Giới hạn quyền **POST** chặt hơn nếu collector chỉ cần GET.
- Cân nhắc Spring Security và CSRF khi cấu hình POST; không tắt CSRF toàn hệ thống tùy tiện.
- Không đưa password, token hay thông tin khách hàng vào StartupStep tags.
- Ghi lại instance nào được đo, ai đã drain và kết quả có được lưu thành công hay không.
- Dùng một owner/collector cho việc drain; những người khác đọc bản sao đã xuất.
- Kiểm tra nội dung JSON trước khi tải lên một hệ thống bên thứ ba.

Việc GET rồi copy file là cách an toàn hơn để phục vụ phân tích một lần. Nếu POST dùng như cơ chế chuyển giao, nó không phải transaction giữa buffer JVM và kho dữ liệu đích: failure sau khi nhận response có thể làm mất dữ liệu.

## 15. Bộ câu hỏi kiểm thử

**Câu 1:** BufferingApplicationStartup(256) có nghĩa 256 MB không?  
**Đáp án:** Không, capacity là số event/step được giữ theo chính sách buffer.

**Câu 2:** Bộ đệm đầy thì lưu những step gần nhất hay những step được ghi trước?  
**Đáp án:** Những event đã ghi trước; step mới không tự thay thế step cũ.

**Câu 3:** getBufferedTimeline có xóa dữ liệu không?  
**Đáp án:** Không, đây là snapshot.

**Câu 4:** drainBufferedTimeline khác snapshot ở đâu?  
**Đáp án:** Trả dữ liệu đang có và loại chúng khỏi buffer.

**Câu 5:** Gọi GET /actuator/startup hai lần liên tiếp có làm sự kiện cũ mất đi?  
**Đáp án:** Không, trừ khi có một bên khác drain hoặc dữ liệu thay đổi vì nguyên nhân khác.

**Câu 6:** POST /actuator/startup có an toàn để gọi thử rồi gọi lại lấy dữ liệu y như cũ?  
**Đáp án:** Không. POST drain; không có replay tự động.

**Câu 7:** Vì sao phải setApplicationStartup trước SpringApplication.run?  
**Đáp án:** Vì startup đã trôi qua không thể được recorder gắn muộn đo ngược.

**Câu 8:** Một event vắng mặt có thể do những lý do nào?  
**Đáp án:** Không được instrument, filter, buffer đầy, chưa end(), đã drain hoặc xảy ra ở lần JVM khác.

**Câu 9:** addFilter nhiều lần kết hợp theo OR hay AND?  
**Đáp án:** AND; nếu cần OR, viết một predicate có toán tử OR.

**Câu 10:** Có thể cộng mọi duration để ra tổng startup?  
**Đáp án:** Không đáng tin vì các step có thể nested/overlap.

**Câu 11:** Sau drain mà recorder còn sống, nó có thể nhận step mới không?  
**Đáp án:** Có nếu bước mới được instrument và còn capacity, nhưng các bước bị bỏ qua trước drain không tự replay.

**Câu 12:** Khi pod restart, bộ đệm cũ còn không?  
**Đáp án:** Không, trừ khi đã export dữ liệu ra kho bền vững.

**Câu 13:** Khi app fail trước Actuator Ready, có chắc gọi được /actuator/startup không?  
**Đáp án:** Không. Cần phương án logging/export/JFR khác nếu đo startup failure là yêu cầu chính.

**Câu 14:** POST startup có xóa application.ready.time metric không?  
**Đáp án:** Không, đó là hai cơ chế đo khác nhau.

**Câu 15:** Khi muốn phân tích class loading và GC cùng startup, cân nhắc công cụ nào?  
**Đáp án:** Java Flight Recorder với FlightRecorderApplicationStartup.

## 16. Checklist triển khai đo startup

1. Đặt đúng Spring Boot và Java version, đọc API của phiên bản thực tế.
2. Tạo BufferingApplicationStartup trước run và gắn bằng setApplicationStartup.
3. Chọn capacity dựa trên số lượng step thực, không suy từ số byte hoặc thời gian.
4. Đảm bảo custom StartupStep được end trong finally khi cần.
5. Nếu dùng filter, kiểm tra AND semantics và gắn trước khi chạy.
6. Phân biệt thiếu data do capacity, filter, instrumentation hoặc drain.
7. Đọc snapshot bằng GET trước; chỉ POST khi có chủ đích xả.
8. Lưu dữ liệu cùng build, profile, instance, timestamp và điều kiện startup.
9. Không coi buffer trong RAM là storage bền vững qua restart.
10. Bảo vệ startup endpoint, đặc biệt quyền POST và custom tags.
11. Đo heap và response size khi tăng capacity.
12. Không cộng nested durations như tổng startup time.
13. So sánh với application.started.time và application.ready.time.
14. Có phương án JFR/log nếu startup failure xảy ra trước khi HTTP endpoint truy cập được.
15. Kiểm tra việc thu thập khi có nhiều Pod để tránh mất một phần rollout.

**Kết luận:** BufferingApplicationStartup có bộ đệm giới hạn theo **số StartupStep event**; khi đầy, bước mới không được ghi tiếp. **Snapshot/GET không xóa**; **drain/POST lấy và xóa event** khỏi recorder. Dữ liệu không tự tồn tại qua JVM restart. Muốn đo startup tin cậy, phải thiết kế đồng thời **điểm bắt đầu ghi, capacity, filter, vòng đời snapshot/drain, bảo mật, nơi lưu bền vững và cách xác minh dữ liệu đầy đủ**, thay vì chỉ bật Actuator rồi xem một response JSON.

### Tài liệu tham khảo

- [Spring Boot 3.3: Application Startup Tracking](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3: BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html)
- [Spring Boot 3.3: Actuator Startup REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html)
- [Spring Boot 3.3: Endpoints và Web Exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3: Application Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
