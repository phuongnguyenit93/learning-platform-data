# Nhóm vị trí nạp: dấu phẩy, dấu chấm phẩy và tác động đến ghi đè

## 1. Vấn đề: nhiều vị trí cấu hình nhưng không phải lúc nào cũng ưu tiên theo cùng cách

Spring Boot cho phép đặt tệp cấu hình ở nhiều vị trí. Chẳng hạn, một ứng dụng có thể có cấu hình chung trong `classpath:/cfg/` và cấu hình bổ sung trong `classpath:/ext/`. Cả hai thư mục đều có thể chứa `application.properties` và các biến thể theo profile như `application-prod.properties`, `application-live.properties`.

Khi một thuộc tính được khai báo tại nhiều vị trí, ứng dụng phải chọn một giá trị có hiệu lực. Cách chọn phụ thuộc vào **thứ tự nạp các vị trí**, **profile đang hoạt động** và **cách nhóm vị trí**.

Hai chuỗi trông gần giống nhau nhưng có ý nghĩa khác nhau:

```properties
# Hai nhóm vị trí riêng biệt
spring.config.location=classpath:/cfg/,classpath:/ext/

# Một nhóm chứa hai vị trí cùng mức
spring.config.location=classpath:/cfg/;classpath:/ext/
```

- Dấu phẩy `,` **phân tách các nhóm vị trí**. Trong ví dụ đầu, `cfg` là nhóm trước, `ext` là nhóm sau. Spring Boot xử lý các tệp thuộc `cfg` rồi đến `ext`; những tệp của nhóm sau có thể ghi đè nhóm trước.
- Dấu chấm phẩy `;` **gộp các vị trí vào cùng một nhóm**. Trong ví dụ thứ hai, `cfg` và `ext` được xem ở cùng một mức khi xử lý các biến thể theo profile. Thứ tự profile có thể quyết định tệp nào ghi đè tệp nào giữa hai vị trí.

Đây là cơ chế **location groups** của Config Data trong Spring Boot, áp dụng khi dùng `spring.config.location` hoặc `spring.config.additional-location`. Dấu chấm phẩy không phải chỉ là dấu phẩy viết theo cách khác.

Một nhóm gồm nhiều vị trí vẫn có thứ tự nội bộ: nếu hai vị trí trong cùng nhóm cung cấp cùng khóa ở cùng mức/profile, vị trí được xét sau có thể ghi đè vị trí trước. “Cùng mức” đặc biệt quan trọng khi **có nhiều profile**; không có nghĩa tất cả giá trị trong nhóm đều ngang nhau và Spring chọn ngẫu nhiên.

## 2. Ba khái niệm cần tách bạch

### Vị trí nạp

Một location có thể là thư mục, ví dụ `classpath:/cfg/`, `file:./config/`, hoặc một tệp cụ thể như `file:./ops/application.properties`.

- `classpath:` chỉ tài nguyên trên classpath; trong ví dụ JAR thực thi, các tài nguyên dưới `src/main/resources` được đóng gói vào JAR.
- `file:` chỉ tài nguyên từ hệ thống tệp. Đường dẫn `./` được hiểu theo thư mục làm việc lúc chạy ứng dụng.
- Khi khai báo **thư mục** qua `spring.config.location`, cần đặt dấu `/` cuối đường dẫn; Spring Boot dùng `spring.config.name` (mặc định là `application`) để tìm tên tệp tương ứng.
- Với vị trí **tệp cụ thể**, Spring Boot nạp tệp theo địa chỉ đã chỉ ra và còn xem xét các biến thể theo profile nếu thích hợp.

### Profile

Một profile như `prod` hoặc `live` cho phép Spring Boot dùng thêm `application-prod.properties` hoặc `application-live.properties`. Nếu bật nhiều profile theo thứ tự `prod,live`, quy tắc “profile được xét sau có thể ghi đè profile trước” tham gia vào việc quyết định giá trị.

Điều này không có nghĩa mọi tệp `application-live.properties` đều thắng mọi tệp `application-prod.properties` trong tất cả bố cục. **Ranh giới nhóm vị trí** có thể khiến cả nhóm xử lý sau ghi đè nhóm xử lý trước.

### Ghi đè thuộc tính

Cùng một khóa, ví dụ `lab.marker`, có thể xuất hiện trong nhiều tệp. Khi các nguồn được nạp và sắp xếp, Spring `Environment` tra cứu giá trị có hiệu lực theo thứ tự ưu tiên; mã Java nhận giá trị đó qua `Environment`, `@Value` hoặc `@ConfigurationProperties`.

Chúng ta sẽ giữ nguyên **mọi tệp** và **mọi profile** ở hai lần chạy chính, chỉ đổi dấu `,` thành `;`. Nếu kết quả khác nhau, nguyên nhân là **cách nhóm vị trí**, không phải nội dung tệp đã bị sửa.

## 3. Dựng ứng dụng quan sát tối thiểu

Dùng một dự án Spring Boot với Java 17 trở lên (ví dụ Spring Boot 3.x), có thể tạo JAR thực thi bằng Maven hoặc Gradle. Cấu trúc dữ liệu cho thí nghiệm:

```text
src/main/
├── java/com/example/locationlab/
│   └── LocationLabApplication.java
└── resources/
    ├── cfg/
    │   ├── application.properties
    │   ├── application-prod.properties
    │   └── application-live.properties
    └── ext/
        ├── application.properties
        ├── application-prod.properties
        └── application-live.properties
```

Không cần tạo `src/main/resources/application.properties` ở classpath gốc: ta sẽ dùng `spring.config.location` để chỉ rõ hai thư mục cần đọc. Điều này cũng giúp tránh nhầm lẫn với vị trí mặc định.

Tạo `LocationLabApplication.java`:

```java
package com.example.locationlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LocationLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(LocationLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showEffectiveConfig(Environment environment) {
        return args -> {
            String marker = environment.getProperty("lab.marker");
            String note = environment.getProperty("lab.note");

            System.out.println("=== LOCATION GROUP LAB ===");
            System.out.println("lab.marker = " + marker);
            System.out.println("lab.note   = " + note);
            System.out.println("==========================");
        };
    }
}
```

`ApplicationRunner` chỉ đọc hai khóa thử nghiệm khi ứng dụng khởi động xong. `lab.marker` là khóa dùng để chứng minh ưu tiên; `lab.note` được dùng để xác nhận tệp `application-live.properties` trong thư mục `ext` có thực sự được nạp.

Không cần tự đọc từng file trong Java. Đối tượng `Environment` đã tổng hợp các nguồn do Spring Boot chuẩn bị. Nếu có cấu hình bên ngoài thí nghiệm khai báo `lab.marker` từ biến môi trường, JVM system property hoặc tham số dòng lệnh, nguồn đó có thể ghi đè kết quả. Hãy chạy trong môi trường không có `LAB_MARKER`, `-Dlab.marker` hay `--lab.marker` ngoài những đối số được nêu.

## 4. Tạo bộ dữ liệu có chủ đích

Mỗi tệp chứa những giá trị sau. Chúng ta cố tình để tệp `ext/application-live.properties` **không khai báo `lab.marker`**; nếu cả hai tệp `-live` đều định nghĩa khóa và thư mục `ext` đứng sau, hai lần chạy có thể cho cùng kết quả và che mất sự khác nhau giữa dấu phẩy với dấu chấm phẩy.

### Nhóm tài nguyên cfg

`src/main/resources/cfg/application.properties`:

```properties
lab.marker=cfg-base
```

`src/main/resources/cfg/application-prod.properties`:

```properties
lab.marker=cfg-prod
```

`src/main/resources/cfg/application-live.properties`:

```properties
lab.marker=cfg-live
```

### Nhóm tài nguyên ext

`src/main/resources/ext/application.properties`:

```properties
lab.marker=ext-base
```

`src/main/resources/ext/application-prod.properties`:

```properties
lab.marker=ext-prod
```

`src/main/resources/ext/application-live.properties`:

```properties
lab.note=ext-live-loaded
```

Cả sáu file đều có mặt trong JAR. Chỉ có **năm** file khai báo `lab.marker`; file cuối chỉ có `lab.note`. Đó là dụng ý của thí nghiệm.

Bảng tóm tắt:

| Thư mục | File | `lab.marker` | Khóa phụ |
| --- | --- | --- | --- |
| `cfg` | `application.properties` | `cfg-base` | — |
| `cfg` | `application-prod.properties` | `cfg-prod` | — |
| `cfg` | `application-live.properties` | `cfg-live` | — |
| `ext` | `application.properties` | `ext-base` | — |
| `ext` | `application-prod.properties` | `ext-prod` | — |
| `ext` | `application-live.properties` | Không có | `lab.note=ext-live-loaded` |

Sau khi tạo file, đóng gói một lần, chẳng hạn chạy `./gradlew bootJar` ở môi trường có Gradle Wrapper hoặc `mvn package` ở môi trường Maven phù hợp. Đặt tên minh họa cho JAR đã đóng gói là `app.jar` trong các lệnh sau; thay bằng đường dẫn JAR thực tế của dự án.

Đối với hai lần chạy chính, luôn giữ đúng profile:

```text
spring.profiles.active = prod,live
```

Profile `prod` đứng trước, `live` đứng sau. Ta sẽ không đổi thứ tự này khi so sánh dấu phân cách.

## 5. Thí nghiệm A: dấu phẩy tạo hai nhóm độc lập

Chạy ứng dụng với `spring.config.location` có dấu phẩy:

```bash
java -jar app.jar \
  '--spring.config.location=classpath:/cfg/,classpath:/ext/' \
  '--spring.profiles.active=prod,live'
```

Trên Windows PowerShell, có thể dùng một dòng:

```powershell
java -jar app.jar '--spring.config.location=classpath:/cfg/,classpath:/ext/' '--spring.profiles.active=prod,live'
```

Kết quả mong đợi:

```text
=== LOCATION GROUP LAB ===
lab.marker = ext-prod
lab.note   = ext-live-loaded
==========================
```

Tại sao `ext-prod` thắng `cfg-live`, dù profile `live` đứng sau `prod`?

Vì dấu phẩy tạo hai location group nối tiếp:

```text
Nhóm 1: classpath:/cfg/
    cfg/application.properties
    cfg/application-prod.properties
    cfg/application-live.properties
               |
               v
Nhóm 2: classpath:/ext/
    ext/application.properties
    ext/application-prod.properties
    ext/application-live.properties
```

Trong nhóm `cfg`, giá trị `cfg-live` ghi đè `cfg-prod` và `cfg-base`. Sang **nhóm `ext` xử lý sau**, `ext-base` rồi `ext-prod` lại cung cấp `lab.marker` và có thể ghi đè giá trị từ nhóm trước. Tệp `ext/application-live.properties` không định nghĩa `lab.marker` nên không thay đổi giá trị đã được chọn là `ext-prod`.

Nếu nhìn theo các file có khai báo khóa `lab.marker`, ta có thể hình dung thứ tự từ trước đến sau:

```text
cfg/base  -> cfg-prod -> cfg-live -> ext-base -> ext-prod
  |            |           |            |           |
cfg-base     cfg-prod    cfg-live     ext-base     ext-prod
                                                       ^
                                             giá trị thắng cuối
```

Tệp `ext/application-live.properties` vẫn được nạp: bằng chứng là `lab.note` nhận `ext-live-loaded`. Việc **không có khóa `lab.marker`** trong tệp này không làm xóa giá trị của khóa do tệp `ext/application-prod.properties` cung cấp.

Kết luận cho cách viết có dấu phẩy: **quy tắc “vị trí/nhóm sau ghi đè nhóm trước” có thể thắng sự ưu tiên profile giữa hai nhóm**. Do đó, ở hai thư mục khác nhóm, không thể chỉ nhìn hậu tố `-live` và `-prod` để đoán kết quả.

## 6. Thí nghiệm B: dấu chấm phẩy đặt hai vị trí cùng mức

Không sửa bất kỳ tệp nào; chỉ thay dấu phẩy giữa hai vị trí thành dấu chấm phẩy và giữ nguyên `prod,live`:

```bash
java -jar app.jar \
  '--spring.config.location=classpath:/cfg/;classpath:/ext/' \
  '--spring.profiles.active=prod,live'
```

Trong Windows PowerShell:

```powershell
java -jar app.jar '--spring.config.location=classpath:/cfg/;classpath:/ext/' '--spring.profiles.active=prod,live'
```

Kết quả mong đợi:

```text
=== LOCATION GROUP LAB ===
lab.marker = cfg-live
lab.note   = ext-live-loaded
==========================
```

Lần này hai thư mục nằm trong **một location group**:

```text
                 CÙNG MỘT NHÓM
       +-------------------------------+
       | classpath:/cfg/               |
       | classpath:/ext/               |
       +-------------------------------+
               |
               v
         Các file cơ sở
               |
               v
         Các file -prod
               |
               v
         Các file -live
```

Đây là cách mô tả thứ tự ở mức khái niệm: các biến thể theo profile được xét qua các vị trí **trong cùng nhóm**, thay vì hoàn tất mọi profile của `cfg` rồi mới chuyển qua mọi profile của `ext`.

Với `prod,live`, ta lần theo khóa `lab.marker`:

1. Các file cơ sở đưa vào các giá trị `cfg-base` và `ext-base`; trong cùng mức, vị trí `ext` ở sau có thể ghi đè `cfg`.
2. Ở profile `prod`, `cfg/application-prod.properties` cung cấp `cfg-prod` rồi `ext/application-prod.properties` cung cấp `ext-prod`.
3. Ở profile `live`, `cfg/application-live.properties` cung cấp `cfg-live`. Vì `live` được xét sau `prod` trong cùng nhóm, `cfg-live` có thể ghi đè `ext-prod`.
4. `ext/application-live.properties` cũng được nạp, nhưng nó chỉ cung cấp `lab.note`, không có `lab.marker` để ghi đè `cfg-live`.

Kết quả là `cfg-live`. Trong hai lần chạy A và B, tệp `cfg/application-live.properties` vẫn chứa cùng một giá trị; chính việc **đưa hai thư mục về cùng cấp ưu tiên theo profile** đã làm kết quả đổi từ `ext-prod` sang `cfg-live`.

### So sánh trực diện

| Yếu tố | Dấu phẩy `,` | Dấu chấm phẩy `;` |
| --- | --- | --- |
| Cấu hình | `classpath:/cfg/,classpath:/ext/` | `classpath:/cfg/;classpath:/ext/` |
| Nhóm vị trí | Hai nhóm: `cfg` rồi `ext` | Một nhóm: `cfg` và `ext` |
| Profile | `prod,live` | `prod,live` |
| Tệp đã tạo | Giống nhau | Giống nhau |
| `lab.note` | `ext-live-loaded` | `ext-live-loaded` |
| **`lab.marker`** | **`ext-prod`** | **`cfg-live`** |
| Lý do | Nhóm `ext` được xử lý sau nhóm `cfg` | Các file `-live` được xét sau `-prod` trong cùng nhóm |

Đây là điểm trung tâm của bài: **dấu phân cách vị trí có thể làm thay đổi kết quả ghi đè khi có nhiều profile**, dù danh sách vị trí và nội dung tệp không đổi.

## 7. Vì sao không thể chỉ nói “file sau luôn thắng”?

Câu “file sau thắng” đúng khi ta đã xác định được **thứ tự xét thực sự** của các nguồn có cùng khóa. Nhưng thứ tự đó không nhất thiết chính là thứ tự tên thư mục được gõ trên dòng lệnh.

Với dấu phẩy:

```text
group 1: cfg  [base, prod, live]
group 2: ext  [base, prod, live]
```

Các biến thể trong nhóm `cfg` được xét trước khi sang `ext`. Vì vậy, `ext-prod` có thể ghi đè `cfg-live`.

Với dấu chấm phẩy:

```text
group 1: [cfg, ext]
         [base] -> [prod] -> [live]
```

Cả hai vị trí chia sẻ cấp ưu tiên theo profile; `cfg-live` được xét sau `ext-prod` trong cùng nhóm.

Nếu `ext/application-live.properties` cũng chứa `lab.marker=ext-live`, cả hai cách có thể cùng cho `ext-live`: tệp thuộc profile cuối cùng ở vị trí `ext` phía sau có khóa đó. Khi như vậy, ta **không thể kết luận dấu phẩy và dấu chấm phẩy là tương đương** chỉ dựa vào một lần quan sát giống nhau. Phải xây dựng dữ liệu sao cho hai chiến lược có khả năng tạo kết quả khác nhau, như thí nghiệm ở trên.

Tương tự, nếu chỉ bật một profile và mọi file trùng khóa đều nằm ở đúng một vị trí, tác động của việc nhóm có thể khó thấy. Giá trị thực tiễn của location groups xuất hiện rõ nhất khi kết hợp **nhiều vị trí, nhiều profile và những khóa có mặt không đồng đều**.

## 8. Thí nghiệm C: đảo thứ tự profile

Giữ cấu hình có dấu chấm phẩy, nhưng đổi thứ tự profile từ `prod,live` sang `live,prod`:

```bash
java -jar app.jar \
  '--spring.config.location=classpath:/cfg/;classpath:/ext/' \
  '--spring.profiles.active=live,prod'
```

Kết quả mong đợi:

```text
lab.marker = ext-prod
lab.note   = ext-live-loaded
```

Vì trong cùng location group, profile `prod` giờ được xét sau `live`, `ext/application-prod.properties` có thể ghi đè `cfg/application-live.properties` đối với `lab.marker`.

Đối chiếu:

| Nhóm vị trí | Thứ tự profile | Kết quả `lab.marker` |
| --- | --- | --- |
| `cfg;ext` | `prod,live` | `cfg-live` |
| `cfg;ext` | `live,prod` | `ext-prod` |
| `cfg,ext` | `prod,live` | `ext-prod` |
| `cfg,ext` | `live,prod` | `ext-prod` |

Hai dòng dùng dấu phẩy có cùng kết quả trong bộ dữ liệu này vì nhóm `ext` được xử lý sau nhóm `cfg`, và trong nhóm `ext` chỉ file `-prod` chứa `lab.marker`. Hai dòng dùng dấu chấm phẩy khác nhau vì profile đứng sau thay đổi.

Đừng nhầm dấu phẩy trong `spring.profiles.active=prod,live` với dấu phẩy trong `spring.config.location=...`. Chúng thuộc **hai thuộc tính khác nhau**: một bên liệt kê profile, một bên phân tách location groups. Không thay dấu phẩy của `spring.profiles.active` bằng dấu chấm phẩy theo quy tắc location group.

## 9. Một cấu hình có nhiều nhóm hơn

Trong ứng dụng lớn, có thể muốn một số vị trí cùng cấp, còn một số vị trí phải được ưu tiên hơn hẳn. Khi đó ta phối hợp hai dấu:

```text
classpath:/defaults/;classpath:/shared/,
file:./ops/;file:./secrets/
```

Có thể hình dung:

```text
Nhóm 1
    classpath:/defaults/
    classpath:/shared/
              |
              v
Nhóm 2
    file:./ops/
    file:./secrets/
```

Dấu chấm phẩy đặt hai vị trí trong một nhóm; dấu phẩy phân cách nhóm 1 và nhóm 2. Khi xét cùng một khóa, nhóm xử lý sau có cơ hội ghi đè nhóm trước. Trong nội bộ nhóm, thứ tự profile được áp dụng qua các vị trí thuộc nhóm đó.

Ví dụ `defaults` và `shared` đều chứa cấu hình đóng gói theo profile, còn `ops` và `secrets` đại diện cho các vị trí ngoài JAR. Cách phân nhóm diễn đạt rõ ý định: nguồn cấu hình vận hành có thể ghi đè nhóm mặc định, còn những vị trí trong cùng nhóm được xét ở cùng cấp profile.

Tên thư mục `secrets` ở đây chỉ là minh họa về location; việc dùng `application.properties` trong một thư mục có tên như vậy **không tự tạo cơ chế bảo vệ bí mật**. Với dữ liệu nhạy cảm cần áp dụng cách cấp bí mật và kiểm soát truy cập phù hợp với môi trường triển khai.

## 10. spring.config.location và spring.config.additional-location

Hai thuộc tính đều hỗ trợ khai báo vị trí và cách nhóm, nhưng khác nhau ở quan hệ với danh sách tìm kiếm mặc định.

### 10.1. spring.config.location: thay thế vị trí mặc định

Trong hai thí nghiệm chính, ta dùng:

```properties
spring.config.location=classpath:/cfg/;classpath:/ext/
```

Khi được đặt, `spring.config.location` **thay thế** các vị trí tìm kiếm mặc định. Vì vậy, danh sách nguồn Config Data được chỉ ra trực tiếp và dễ kiểm soát hơn. Điều này không xóa những loại PropertySource khác như system properties hoặc biến môi trường; nó thay danh sách tìm file cấu hình ứng dụng mặc định.

Đặt `spring.config.location` bằng tham số dòng lệnh hoặc biến môi trường từ trước khi Spring Boot nạp Config Data. Không nên kỳ vọng một tệp `application.properties` thông thường tự xác định lại danh sách tìm kiếm dùng để tìm chính nó.

### 10.2. spring.config.additional-location: bổ sung vào vị trí mặc định

Nếu muốn giữ các vị trí Spring Boot vẫn quét mặc định rồi nạp thêm nguồn, dùng:

```bash
java -jar app.jar \
  '--spring.config.additional-location=classpath:/cfg/;classpath:/ext/' \
  '--spring.profiles.active=prod,live'
```

Khi dùng `spring.config.additional-location`, các vị trí bổ sung được thêm **sau các vị trí mặc định** và có thể ghi đè giá trị từ vị trí mặc định. Dấu chấm phẩy vẫn có ý nghĩa nhóm các vị trí bổ sung với nhau.

Để thí nghiệm chỉ phản ánh `cfg` và `ext`, ta chọn `spring.config.location`; trong ứng dụng thật, `additional-location` thường tiện hơn khi cần giữ file `application.yml` mặc định của ứng dụng.

Không nên đồng thời thay `spring.config.location` và thêm `spring.config.additional-location` trong cùng một thí nghiệm mới học nếu chưa ghi rõ toàn bộ danh sách nguồn; nếu không, khó biết giá trị đến từ đâu.

### 10.3. spring.config.import là cơ chế khác

Một file cấu hình còn có thể khai báo `spring.config.import` để nhập dữ liệu từ nơi khác. Đó là cơ chế nhập bổ sung từ **bên trong tài liệu cấu hình**; thứ tự nhập có quy tắc riêng. Không lấy kết luận về dấu `,` / `;` trong `spring.config.location` rồi tự động áp đặt nguyên xi cho `spring.config.import`.

Bài này tập trung vào **location groups** qua hai thuộc tính location, để người học nhìn rõ tác dụng của ký tự phân cách.

## 11. Quy tắc cú pháp dễ sai khi chạy thật

### 11.1. Trích dẫn đối số chứa dấu chấm phẩy

Trong Bash và PowerShell, dấu `;` có vai trò phân tách lệnh nếu xuất hiện ở vị trí cú pháp phù hợp. Vì thế, hãy **đặt toàn bộ đối số có dấu chấm phẩy trong cặp dấu nháy**.

Đúng với Bash hoặc PowerShell:

```bash
java -jar app.jar '--spring.config.location=classpath:/cfg/;classpath:/ext/'
```

Không dùng dạng không trích dẫn sau để thử semicolon:

```text
java -jar app.jar --spring.config.location=classpath:/cfg/;classpath:/ext/
```

Ở dạng này, shell có thể coi phần sau `;` là một lệnh mới. Lỗi phát sinh ở shell **trước khi Spring Boot nhận được chuỗi cần xử lý**, nên không phải bằng chứng về quy tắc location groups.

Với `cmd.exe` trên Windows, có thể dùng dấu nháy kép quanh cả đối số:

```bat
java -jar app.jar "--spring.config.location=classpath:/cfg/;classpath:/ext/" "--spring.profiles.active=prod,live"
```

### 11.2. Đường dẫn thư mục kết thúc bằng /

Đúng:

```text
classpath:/cfg/
file:./config/
```

Không nên khai báo thư mục dạng `classpath:/cfg` rồi kỳ vọng Spring Boot tự hiểu là thư mục. Quy tắc cú pháp vị trí yêu cầu slash cuối cho location là directory.

### 11.3. Vị trí không tồn tại

Một location bắt buộc mà không tìm thấy có thể làm ứng dụng không khởi động với lỗi liên quan đến Config Data. Nếu thực sự muốn một location được phép vắng mặt, thêm tiền tố `optional:` cho location đó:

```text
optional:classpath:/cfg/;optional:file:./ops/
```

Mỗi vị trí tùy chọn được khai báo rõ ràng. `optional:` thay đổi cách xử lý trường hợp không tìm thấy, **không tự làm thay đổi mức ưu tiên hoặc biến dấu chấm phẩy thành dấu phẩy**.

### 11.4. Đừng nhầm vị trí với tên file

`spring.config.name` mặc định là `application`. Với một directory location, Spring Boot tìm các tên tương ứng như `application.properties`, `application.yml` và biến thể profile. Nếu chuyển tên thành `service` qua `spring.config.name=service`, phải chuẩn bị các file như `service.properties`, `service-prod.properties`. Một thí nghiệm có tên file không khớp sẽ làm bạn hiểu sai kết quả ưu tiên.

### 11.5. Tránh nguồn ghi đè ngoài thí nghiệm

Đừng truyền đồng thời `--lab.marker=something` hoặc `-Dlab.marker=something` khi so sánh các nhóm file. Theo thứ tự PropertySource thông thường, những nguồn đó có ưu tiên cao hơn Config Data và làm hai lần chạy đều hiện cùng giá trị. Tương tự, cần kiểm tra các biến môi trường, test properties và cấu hình nhập thêm có thể ghi đè khóa.

## 12. Cách chẩn đoán khi kết quả thực tế khác kỳ vọng

Nếu chạy thí nghiệm A nhưng màn hình hiện `cfg-live` thay cho `ext-prod`, hãy kiểm tra theo trình tự:

1. **Đối số mà ứng dụng thực nhận:** `spring.config.location` chứa dấu `,` hay `;`? Cả chuỗi đã được trích dẫn đúng trong shell chưa?
2. **Profile hoạt động:** có đúng `prod,live`? Nếu profile `live` không hoạt động, file `application-live.properties` sẽ không đóng góp như thiết kế.
3. **Tài nguyên trong JAR:** các file trong `cfg/` và `ext/` đã thực sự được đóng gói chưa? Chạy lại lệnh đóng gói sau khi tạo resource.
4. **Khóa trong từng file:** `ext/application-prod.properties` có `lab.marker=ext-prod` không? `ext/application-live.properties` có vô tình thêm `lab.marker` không?
5. **Tiền tố của location:** cả hai đều dùng `classpath:` và kết thúc bằng `/`? Nếu một đường dẫn dùng `file:`, có thể thư mục làm việc hoặc nội dung nguồn đã khác.
6. **Nguồn ưu tiên cao:** có biến môi trường `LAB_MARKER` hoặc tùy chọn `-Dlab.marker`, `--lab.marker` còn sót không?
7. **Phiên chạy mới:** ứng dụng đã được dừng rồi chạy lại với đối số mới chưa? Thí nghiệm so sánh cấu hình tại thời điểm khởi động, không phải cập nhật động cho bean đang chạy.

`lab.note=ext-live-loaded` là dấu hiệu hữu ích: nó xác nhận rằng tệp `ext/application-live.properties` được nạp ở cả hai thí nghiệm chính. Nếu `lab.note` là `null`, ta nên kiểm tra profile, đường dẫn, tài nguyên đóng gói và tên khóa trước khi suy luận về việc ghi đè của `lab.marker`.

Nếu dự án có Spring Boot Actuator và các endpoint thích hợp được bật, `env` có thể hỗ trợ xem nguồn của thuộc tính trong môi trường thử nghiệm. Không công khai danh sách cấu hình của ứng dụng thật hoặc in các khóa nhạy cảm khi chẩn đoán.

## 13. Bài tập tự kiểm chứng

Hãy giữ nguyên sáu file chuẩn rồi dự đoán giá trị trước khi khởi động.

**Bài tập 1 — Thay nhóm bằng dấu phẩy:** Với `classpath:/cfg/,classpath:/ext/` và profile `prod,live`, vì sao kết quả là `ext-prod` thay vì `cfg-live`?

**Bài tập 2 — Gộp nhóm:** Với `classpath:/cfg/;classpath:/ext/`, tại sao `cfg-live` lại có thể ghi đè `ext-prod`? Việc file `ext/application-live.properties` không có `lab.marker` tác động thế nào?

**Bài tập 3 — Thêm khóa vào file live ngoài:** Bổ sung `lab.marker=ext-live` trong `ext/application-live.properties`, đóng gói lại và chạy cả hai cách phân nhóm. Trước khi chạy, dự đoán cả hai kết quả. Sau đó giải thích vì sao quan sát giống nhau **không chứng minh** dấu phẩy và dấu chấm phẩy là một.

**Bài tập 4 — Đảo profile:** Với cấu hình semicolon, đổi `prod,live` thành `live,prod`. Giá trị `lab.marker` mới là gì? Điều gì thay đổi trong cách xét profile?

**Bài tập 5 — Đảo nhóm:** Thử `classpath:/ext/,classpath:/cfg/` với `prod,live`. Vì sao thay thứ tự các nhóm có thể làm giá trị từ `cfg` thắng?

**Bài tập 6 — Dùng external files:** Chuyển một nhóm cấu hình sang thư mục ngoài JAR, ví dụ `file:./ops/`. Hãy tự xác định thư mục làm việc, đặt các tệp `application*.properties` thích hợp, dùng `optional:` nếu cần, rồi so sánh các biểu thức dùng `,` và `;`. Chỉ thay một yếu tố trong mỗi lần chạy.

Với mỗi bài, giải thích được ba dữ kiện là đạt mục tiêu: **những vị trí nào đã được nạp**, **chúng thuộc những location group nào**, và **profile nào ghi đè khóa ở mức cuối cùng**.

## 14. Ghi nhớ để áp dụng

Location groups là cách Spring Boot diễn đạt quan hệ ưu tiên giữa **các tập vị trí cấu hình**.

- `,`: kết thúc nhóm hiện tại, bắt đầu nhóm tiếp theo; nhóm xuất hiện sau có thể ghi đè giá trị từ nhóm trước.
- `;`: thêm vị trí vào cùng nhóm; các biến thể theo profile được xét cùng mức giữa các vị trí trong nhóm.
- Profile `prod,live`: profile xuất hiện sau có thể ghi đè profile trước **ở cấp location group**, chứ không tự vượt qua mọi ranh giới nhóm.
- `spring.config.location`: thay vị trí tìm kiếm Config Data mặc định.
- `spring.config.additional-location`: bổ sung vị trí, cho phép cấu hình bổ sung ghi đè cấu hình mặc định.

Trong ví dụ có sáu tệp, hai lệnh chỉ khác đúng một ký tự nhưng cho kết quả khác nhau:

```text
classpath:/cfg/,classpath:/ext/
-> lab.marker = ext-prod

classpath:/cfg/;classpath:/ext/
-> lab.marker = cfg-live
```

Do vậy, khi cấu hình theo profile có vẻ “không được ưu tiên” như mong đợi, đừng chỉ xem tên `application-prod.properties` hoặc `application-live.properties`. Hãy kiểm tra **cách khai báo location groups** trước khi kết luận Spring Boot đang nạp sai file.

Tài liệu tham khảo: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), các phần *External Application Properties*, *Profile Specific Files* và *Location Groups*.