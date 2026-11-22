# Cấu hình BufferingApplicationStartup và giới hạn bộ đệm bước khởi động

Khi một ứng dụng Spring Boot khởi động chậm, dòng log báo tổng thời gian chỉ cho biết ứng dụng đã mất bao lâu. Để điều tra, bạn cần biết Spring đã thực hiện bước nào và bước đó kéo dài bao lâu. Spring Framework cung cấp giao diện `ApplicationStartup` để các thành phần đánh dấu bước khởi động bằng `StartupStep`. Spring Boot cung cấp `BufferingApplicationStartup` để lưu các bước đã hoàn tất vào bộ nhớ. Actuator có thể đọc chính dữ liệu đó qua endpoint `startup`.

## Gắn bộ ghi trước khi gọi run()

Với một ứng dụng web Spring Boot 3.3.x đã có `spring-boot-starter-actuator`, hãy cấu hình trên đối tượng `SpringApplication` trong phương thức `main`. Ví dụ dưới đây thay thế `main` trong lớp ứng dụng sẵn có.

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

// Đặt phương thức này trong lớp ActuatorApplication hiện có.
public static void main(String[] args) {
    SpringApplication application = new SpringApplication(ActuatorApplication.class);
    application.setApplicationStartup(new BufferingApplicationStartup(2048));
    application.run(args);
}
```

Nếu đang dùng lệnh rút gọn `SpringApplication.run(ActuatorApplication.class, args)`, hãy tách thành ba dòng như trên để gắn bộ ghi trước khi Boot bắt đầu chạy. Tại thời điểm đó, những bước đầu của `SpringApplication` cũng có thể được ghi nhận. Chờ đến lúc một bean được tạo mới gắn bộ ghi sẽ bỏ lỡ các bước trước đó. `2048` là dung lượng khởi điểm cho ví dụ. Bạn sẽ chọn giá trị theo số bước quan sát được của ứng dụng.

Khai báo endpoint cần mở qua HTTP trong `application.properties` của môi trường chẩn đoán. Nếu ứng dụng đã có danh sách endpoint được phép truy cập qua HTTP, hãy thêm `startup` vào danh sách đó.

```properties
management.endpoints.web.exposure.include=health,startup
```

Cấu hình trên mở đường truy cập qua HTTP. Lệnh `setApplicationStartup(...)` cung cấp bộ ghi mà endpoint cần. Với cổng mặc định, đường dẫn quản trị mặc định và quyền truy cập phù hợp, bạn có thể xem số bước và tên các bước trong bộ đệm. Ví dụ dùng `curl` và `jq`.

```bash
curl -fsS http://localhost:8080/actuator/startup | jq '.timeline.events | length'
curl -fsS http://localhost:8080/actuator/startup |
  jq -r '.timeline.events[] | [.startupStep.name, .duration] | @tsv'
```

Mỗi sự kiện có thời điểm bắt đầu, thời điểm kết thúc và `duration`. `startupStep.id` và `parentId` cho phép đối chiếu các bước lồng nhau khi cả hai đều có trong bản ghi. Khi bước con nằm trong khoảng thời gian của bước cha, cộng cả hai khoảng sẽ đếm trùng phần thời gian giao nhau. Hãy đọc các khoảng thời gian và quan hệ cha–con khi tìm bước chậm.

## Bộ đệm đầy thì chuyện gì xảy ra?

Dung lượng truyền vào constructor tính theo **số sự kiện bước khởi động**. Một bước hoàn tất qua `end()` có thể chiếm một chỗ nếu qua bộ lọc và bộ đệm còn chỗ. Các bước có thể kết thúc theo thứ tự khác lúc bắt đầu. Chẳng hạn, bước con thường kết thúc trước bước cha đang bao quanh nó.

Khi đầy, bộ đệm giữ các sự kiện đã lưu và bỏ qua việc lưu sự kiện mới đến. Vì vậy, dung lượng nhỏ có thể làm mất bước kết thúc muộn, kể cả bước cha đã bắt đầu từ sớm. Phần công việc mà bước đó đo vẫn tiếp tục chạy. Dữ liệu bị bỏ qua lúc đầy không thể lấy lại bằng cách đọc hoặc rút bộ đệm sau đó.

| Thao tác | Kết quả | Tác động lên bộ đệm |
| --- | --- | --- |
| `getBufferedTimeline()` hoặc `GET /actuator/startup` | Trả ảnh chụp các sự kiện hiện có | Giữ lại sự kiện để đọc tiếp |
| `drainBufferedTimeline()` hoặc `POST /actuator/startup` | Trả các sự kiện được rút ra | Giải phóng chỗ để nhận bước hoàn tất tiếp theo nếu còn bước phát sinh |

Nếu cần giữ dữ liệu để nhiều người cùng phân tích, hãy lưu kết quả từ `GET`. Khi dùng `POST`, hãy lưu ngay phản hồi vì thao tác đã lấy các sự kiện ra khỏi bộ đệm. Với Spring Security, quyền gửi `POST` còn phụ thuộc cấu hình bảo mật, kể cả kiểm tra CSRF nếu được bật. Tên bước và thẻ có thể lộ tên bean hoặc thông tin nội bộ, nên giới hạn truy cập endpoint cho người vận hành được cấp quyền.

## Thử với bộ đệm hai chỗ

Chương trình sau dùng trực tiếp API ghi bước. Bạn có thể quan sát giới hạn trên một luồng mà không cần chạy máy chủ web. Lưu chương trình vào `StartupBufferDemo.java`.

```java
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.boot.context.metrics.buffering.StartupTimeline;

public class StartupBufferDemo {
    public static void main(String[] args) {
        var startup = new BufferingApplicationStartup(2);
        startup.addFilter(step -> step.getName().startsWith("demo."));

        startup.start("other.ignored").end();
        startup.start("demo.first").end();
        startup.start("demo.second").end();
        startup.start("demo.third").end();

        System.out.println("Snapshot: " + names(startup.getBufferedTimeline()));
        System.out.println("Drain: " + names(startup.drainBufferedTimeline()));
        System.out.println("After drain: " + names(startup.getBufferedTimeline()));

        startup.start("demo.fourth").end();
        System.out.println("After new step: " + names(startup.getBufferedTimeline()));
    }

    private static java.util.List<String> names(StartupTimeline timeline) {
        return timeline.getEvents().stream()
                .map(event -> event.getStartupStep().getName())
                .toList();
    }
}
```

Dùng JDK 17 trở lên. Đặt `spring-boot-3.3.0.jar` và `spring-core-6.1.8.jar` vào thư mục `lib` cạnh tệp Java rồi biên dịch và chạy.

```bash
javac -cp "lib/*" StartupBufferDemo.java
java -cp ".:lib/*" StartupBufferDemo
```

Trên Windows, dùng `java -cp ".;lib/*" StartupBufferDemo`. Kết quả in ra theo thứ tự sau.

```text
Snapshot: [demo.first, demo.second]
Drain: [demo.first, demo.second]
After drain: []
After new step: [demo.fourth]
```

`other.ignored` bị bộ lọc loại nên hai bước đầu có tiền tố `demo.` chiếm đủ hai chỗ. `demo.third` hoàn tất lúc đầy nên không xuất hiện kể cả sau khi rút. `demo.fourth` hoàn tất sau khi đã có chỗ trống nên được lưu.

## Chọn dung lượng và bộ lọc

1. Khởi động lại ứng dụng với cấu hình và tập bean gần với môi trường cần điều tra. Đọc `GET /actuator/startup` trước khi có thao tác rút bộ đệm và ghi lại số sự kiện, tên các bước cần theo dõi.
2. Nếu số sự kiện chạm dung lượng, hãy tăng dung lượng và khởi động lại để so sánh. Chạm ngưỡng là dấu hiệu cần kiểm tra. Nếu lần sau xuất hiện thêm sự kiện trong cùng điều kiện, lần trước có thể đã hết chỗ. Chọn dung lượng đủ cho các cấu hình triển khai cần theo dõi và chừa chỗ khi số bước thay đổi.
3. Khi chỉ quan tâm đến một nhóm bước, gọi `addFilter(...)` trên bộ ghi trước `run()`. Ví dụ, điều kiện `step -> step.getName().startsWith("spring.beans.")` chỉ giữ các bước có tiền tố đó. Nhiều lần gọi `addFilter(...)` kết hợp các điều kiện theo phép **và**. Hãy lấy một bản ghi đủ rộng trước khi lọc để biết bước nào sẽ bị loại. Bước con được giữ có thể tham chiếu tới bước cha đã bị lọc.
4. Cân đối phạm vi thu thập với chi phí giữ sự kiện trong bộ nhớ và kích thước phản hồi HTTP. Khi danh sách rỗng hoặc ngắn bất ngờ, kiểm tra theo thứ tự đã gắn bộ ghi trước `run()` chưa, bộ lọc có loại mất bước cần xem không, có ai vừa rút dữ liệu không và dung lượng có bị chạm ngưỡng không.

Tài liệu Spring Boot 3.3. [API BufferingApplicationStartup](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html) · [REST API của endpoint startup](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html)
