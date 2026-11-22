# Đọc snapshot và lấy dữ liệu startup ra khỏi bộ đệm

Khi điều tra một lần khởi động chậm, bạn có thể cần xem lại cùng một tập sự kiện nhiều lần hoặc chuyển tập sự kiện đó sang nơi lưu trữ. Cả hai thao tác đều dùng đường dẫn mặc định `/actuator/startup`, nhưng phương thức HTTP quyết định dữ liệu có còn trong bộ đệm sau yêu cầu hay không.

| Thao tác | Phản hồi chứa gì? | Bộ đệm sau yêu cầu |
| --- | --- | --- |
| `GET /actuator/startup` | Bản chụp tại thời điểm đọc (snapshot) của các bước đã được ghi và hiện còn trong bộ đệm. | Các sự kiện vừa đọc vẫn còn. |
| `POST /actuator/startup` | Các bước được lấy ra trong lần gọi này (drain). Yêu cầu không cần nội dung gửi kèm. | Các sự kiện vừa trả về đã bị lấy khỏi bộ đệm. |

## Bộ đệm thay đổi như thế nào?

Trước khi chạy ứng dụng, gắn `BufferingApplicationStartup` vào `SpringApplication` để thu thập các bước khởi động. Khi một bước kết thúc và được ghi nhận, bộ thu giữ thông tin về bước đó trong bộ nhớ của tiến trình. Dung lượng hữu hạn: khi đầy, các bước mới có thể bị bỏ qua. Đọc hay lấy dữ liệu ra sau đó đều chỉ làm việc với những gì đã được giữ lại.

Trong Spring Boot 3.3, thao tác đọc của `StartupEndpoint` dùng `getBufferedTimeline()`, còn thao tác ghi dùng `drainBufferedTimeline()`. Cả hai trả về cấu trúc JSON có `springBootVersion` và `timeline`. Hãy xem `timeline.events` để biết các sự kiện được trả về. Mỗi sự kiện có thời điểm bắt đầu, thời điểm kết thúc, thời lượng và thông tin về bước tương ứng, chẳng hạn tên bước trong `startupStep.name`. Trường `timeline.startTime` là mốc bắt đầu của dòng thời gian. Việc lấy các sự kiện ra không đặt lại mốc này hay khởi động lại ứng dụng.

Giả sử bộ đệm đang chứa A và B, các yêu cầu đi đến cùng một tiến trình và không có sự kiện mới xen vào:

1. `GET` lần đầu trả về A và B. Bộ đệm vẫn chứa A và B.
2. `GET` lần hai vẫn trả về A và B.
3. `POST` lấy A và B khỏi bộ đệm và trả chúng trong phản hồi.
4. `GET` tiếp theo trả về mảng rỗng trong `timeline.events`. Nếu gọi `POST` thêm một lần, lần gọi đó cũng trả về danh sách rỗng. Cả hai vẫn có thể trả `200 OK` cùng cấu trúc JSON đầy đủ.

Nếu có bước mới được ghi sau lần lấy dữ liệu, lần đọc tiếp theo có thể thấy các sự kiện mới. Hai bản chụp ở hai thời điểm vì vậy có thể khác nhau ngay cả khi cả hai đều dùng `GET`.

## Thử trên một ứng dụng Spring Boot 3.3

Ví dụ dùng Java 17 trở lên, Gradle và một ứng dụng cục bộ với hai dependency `spring-boot-starter-web` và `spring-boot-starter-actuator`. Tạo ba tệp sau trong một thư mục thử nghiệm riêng.

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

application {
    mainClass = 'demo.StartupDemo'
}
```

**`src/main/java/demo/StartupDemo.java`**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupDemo {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartupDemo.class);
        app.setApplicationStartup(new BufferingApplicationStartup(2048));
        app.run(args);
    }
}
```

**`src/main/resources/application.properties`**

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,startup
management.endpoint.startup.cache.time-to-live=0s
```

Cấu hình chỉ mở `health` và `startup` qua HTTP, lắng nghe trên địa chỉ cục bộ và đặt thời gian lưu phản hồi đọc về 0 để quan sát trực tiếp trạng thái bộ đệm. Ví dụ không thêm Spring Security. Chạy `gradle run` từ thư mục dự án. Sau khi ứng dụng khởi động xong, mở terminal khác và thực hiện các lệnh sau với Bash, `curl` và `jq`:

```bash
set -e
url=http://127.0.0.1:8080/actuator/startup

curl -fsS "$url" -o snapshot-1.json
curl -fsS "$url" -o snapshot-2.json
curl -fsS -X POST "$url" -o drained.json
curl -fsS "$url" -o after-drain.json
curl -fsS -X POST "$url" -o drained-again.json

for file in snapshot-1.json snapshot-2.json drained.json after-drain.json drained-again.json; do
  printf '%s: ' "$file"
  jq -r '.timeline.events | length' "$file"
done

jq -es '
  (.[0].timeline.events | length) > 0
  and (.[0].timeline.events == .[1].timeline.events)
  and (.[0].timeline.events == .[2].timeline.events)
  and (.[3].timeline.events == [])
  and (.[4].timeline.events == [])
' snapshot-1.json snapshot-2.json drained.json after-drain.json drained-again.json
```

Kết quả kỳ vọng là ba tệp đầu có cùng số sự kiện dương, hai tệp cuối có 0 sự kiện và dòng cuối in `true`. Số bước cụ thể phụ thuộc vào ứng dụng. So sánh mảng sự kiện giúp kiểm tra rằng `POST` đã trả về đúng những bước hai lần `GET` nhìn thấy trong lần chạy này. Để lặp lại thử nghiệm với dữ liệu khởi động mới, dừng và chạy lại ứng dụng.

## Chọn thao tác khi vận hành

- **Đọc để chẩn đoán hoặc lưu bản sao.** Dùng `GET` khi muốn xem nhiều lần, chia sẻ dữ liệu với người khác hoặc lưu một bản JSON để đối chiếu. Nếu cần bằng chứng trước khi dọn bộ đệm, hãy lưu bản chụp trước. Khi có bước mới xen vào, bản chụp trước đó và phản hồi của lần lấy dữ liệu có thể khác nhau.
- **Lấy dữ liệu và giải phóng bộ đệm có chủ đích.** Dùng `POST` khi bên gọi có trách nhiệm thu thập và lưu phản hồi, đồng thời chấp nhận rằng các yêu cầu đọc sau sẽ không còn thấy những sự kiện đó. Việc xóa khỏi bộ đệm diễn ra ở máy chủ trước khi bên gọi lưu phản hồi thành công. Nếu bị mất kết nối, gửi lại `POST` không phát lại lô cũ. Lần gọi lại có thể trả về dữ liệu rỗng hoặc lấy các sự kiện mới.
- **Đối chiếu đúng tiến trình.** Mỗi tiến trình ứng dụng có bộ đệm riêng. Nếu một bộ cân bằng tải chuyển `GET` và `POST` đến hai tiến trình khác nhau, kết quả không chứng minh được việc lấy dữ liệu trên cùng một bộ đệm.
- **Phân biệt phản hồi rỗng với lỗi truy cập.** `200 OK` kèm `events: []` cho biết lần gọi đã thành công và không trả về sự kiện nào. Với `404`, kiểm tra đường dẫn quản trị, cấu hình mở endpoint qua HTTP và việc gắn bộ thu lúc khởi động. Nếu ứng dụng có Spring Security và `POST` trả `403`, kiểm tra quyền truy cập và cấu hình CSRF cho yêu cầu ghi.

Đọc thêm về hợp đồng HTTP, bộ đệm và cấu hình Actuator trong tài liệu Spring Boot 3.3. [Actuator Startup API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html), [BufferingApplicationStartup](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/metrics/buffering/BufferingApplicationStartup.html) và [cấu hình endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).
