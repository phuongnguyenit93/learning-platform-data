# Chuỗi nhiều dòng trong YAML: giữ xuống dòng và gộp dòng

## 1. Vì sao cần chuỗi nhiều dòng?

Trong cấu hình Spring Boot, nhiều thuộc tính chỉ cần một dòng: cổng dịch vụ, số lần thử lại, địa chỉ máy chủ. Nhưng có những giá trị tự nhiên gồm nhiều dòng, chẳng hạn:

- Nội dung email hoặc thông báo gửi cho người dùng.
- Văn bản hiển thị trên màn hình chào mừng.
- Câu truy vấn SQL dài hoặc mẫu dữ liệu có cấu trúc.
- Hướng dẫn, đoạn mô tả, điều khoản hay thông điệp có nhiều đoạn.

Có hai nhu cầu khác nhau. Với email, việc xuống dòng là một phần của nội dung nên phải giữ lại. Với đoạn mô tả chỉ được xuống dòng cho dễ đọc trong tệp cấu hình, ứng dụng thường muốn nhận **một chuỗi liên tục**, trong đó các dòng được gộp bằng dấu cách.

YAML giải quyết hai nhu cầu ấy bằng **chuỗi khối (block scalar)**:

- `|` (*literal style*): giữ các dấu xuống dòng giữa những dòng nội dung.
- `>` (*folded style*): gộp những dòng liên tiếp thông thường thành một dòng, ngăn cách bằng dấu cách; các dòng trống vẫn có ý nghĩa phân đoạn.

Hai ký hiệu này quyết định **cách văn bản trong YAML trở thành giá trị chuỗi**. Khi Spring Boot nạp `application.yaml`, ứng dụng nhận giá trị đã được bộ phân tích YAML xử lý, không nhận nguyên trạng phần trình bày trong tệp.

## 2. Hình dung cách YAML xử lý các dòng

Xét hai giá trị cùng được viết trên ba dòng:

~~~yaml
app:
  literal-message: |
    Chào bạn,
    hôm nay hệ thống sẽ bảo trì.
    Cảm ơn bạn.

  folded-message: >
    Chào bạn,
    hôm nay hệ thống sẽ bảo trì.
    Cảm ơn bạn.
~~~

Nếu dùng ký hiệu `\n` để **biểu diễn** ký tự xuống dòng khi giải thích, hai giá trị tương ứng là:

~~~text
app.literal-message
"Chào bạn,\nhôm nay hệ thống sẽ bảo trì.\nCảm ơn bạn.\n"

app.folded-message
"Chào bạn, hôm nay hệ thống sẽ bảo trì. Cảm ơn bạn.\n"
~~~

Trong hai dòng minh họa này, chuỗi `\n` đại diện cho **một ký tự xuống dòng thực sự**. Nó không có nghĩa YAML đã thêm hai ký tự dấu gạch chéo ngược và chữ `n`.

Hãy chú ý ký tự `\n` cuối cùng của cả hai giá trị: đó là **quy tắc kết thúc mặc định** của chuỗi khối. Phần sau sẽ giải thích cách thay đổi nó.

### Phân biệt ba khái niệm

1. **Dòng vật lý trong tệp YAML:** dòng mà bạn nhìn thấy trong trình soạn thảo.
2. **Dấu xuống dòng trong giá trị chuỗi:** ký tự thực sự còn lại sau khi YAML được phân tích.
3. **Dấu xuống dòng ở cuối chuỗi:** ký tự kết thúc sau dòng nội dung cuối; được điều khiển riêng bằng quy tắc *chomping*.

Hai giá trị có thể chiếm cùng số dòng trên màn hình nhưng tạo ra chuỗi hoàn toàn khác nhau.

## 3. Ký hiệu |: giữ các dấu xuống dòng

`|` phù hợp khi **cách chia dòng là một phần của ý nghĩa**.

~~~yaml
mail:
  subject: "Thông báo bảo trì"
  body: |
    Xin chào,

    Dịch vụ sẽ bảo trì từ 22:00 đến 23:00.
    Vui lòng lưu công việc trước thời điểm này.

    Trân trọng,
    Đội vận hành
~~~

Giá trị của `mail.body` giữ dấu xuống dòng giữa những dòng văn bản. Dòng trống giữa các đoạn cũng được giữ. Với mặc định `|`, chuỗi còn có một dấu xuống dòng ở cuối dòng `Đội vận hành`.

Khi gửi nội dung qua một API email nhận chuỗi thuần, văn bản có thể được giữ thành nhiều đoạn như mong muốn. Nếu gửi bằng HTML, dấu xuống dòng của chuỗi không tự biến thành thẻ `<br>`; việc hiển thị còn phụ thuộc định dạng nội dung và ứng dụng nhận.

Một ví dụ khác là chuỗi nhiều dòng dùng làm banner:

~~~yaml
app:
  banner: |-
    -------------------------
    ỨNG DỤNG ĐANG BẢO TRÌ
    Vui lòng quay lại sau.
    -------------------------
~~~

Ở đây, `|-` vừa giữ các dấu xuống dòng **bên trong** banner, vừa loại dấu xuống dòng **cuối** chuỗi. Nhờ đó, mã Java có thể tự quyết định có thêm một dòng trống sau banner hay không.

### Khi nào nên chọn |?

- Nội dung email dạng văn bản thuần, thông báo cần chia đoạn cụ thể.
- Mẫu xuất văn bản, chữ ký, banner, câu lệnh mà ranh giới dòng có ý nghĩa.
- Dữ liệu muốn bảo toàn cấu trúc dòng để xử lý tiếp.

`|` giữ dấu xuống dòng, nhưng vẫn chịu quy tắc **thụt lề và khoảng trắng** của YAML. Nó không có nghĩa mọi dấu cách dùng để thụt lề trong tệp đều trở thành nội dung chuỗi.

## 4. Ký hiệu >: gộp những dòng để viết văn bản cho dễ đọc

`>` hữu ích khi nội dung là một đoạn văn dài, còn việc chia thành nhiều dòng trong tệp chỉ nhằm giúp người soạn dễ xem và quản lý phiên bản.

~~~yaml
app:
  description: >-
    Dịch vụ này xử lý yêu cầu đăng ký tài khoản
    và gửi email xác nhận cho người dùng
    sau khi dữ liệu được kiểm tra hợp lệ.
~~~

Giá trị nhận được là:

~~~text
"Dịch vụ này xử lý yêu cầu đăng ký tài khoản và gửi email xác nhận cho người dùng sau khi dữ liệu được kiểm tra hợp lệ."
~~~

Dấu `>` thay những dấu xuống dòng giữa các dòng văn bản thông thường bằng **một dấu cách**. Dấu `-` loại dấu xuống dòng ở cuối chuỗi.

### Dòng trống tạo ranh giới đoạn

`>` không gộp mọi thứ thành một dòng duy nhất. Khi có một dòng trống giữa hai nhóm dòng văn bản, ranh giới đoạn được giữ lại:

~~~yaml
app:
  description: >-
    Đầu tiên, người dùng nhập thông tin
    và gửi yêu cầu đăng ký.

    Sau đó, hệ thống gửi email
    để xác nhận địa chỉ liên hệ.
~~~

Kết quả có thể biểu diễn như sau:

~~~text
"Đầu tiên, người dùng nhập thông tin và gửi yêu cầu đăng ký.\nSau đó, hệ thống gửi email để xác nhận địa chỉ liên hệ."
~~~

Một dòng trống giữa hai đoạn trong YAML tương ứng với một ký tự xuống dòng giữa hai đoạn trong giá trị đã được gộp. Nếu cần nhiều dòng trống rõ ràng, phải xét chính xác số dòng trống và cách kết thúc khối.

### Dòng được thụt lề thêm là trường hợp đặc biệt

Trong chuỗi `>`, dòng có mức thụt lề **sâu hơn mức nội dung thông thường** được gọi là dòng *more-indented*. YAML giữ các dấu xuống dòng liên quan đến phần được thụt lề thêm, thay vì gộp chúng theo quy tắc thông thường.

~~~yaml
help:
  message: >-
    Các bước thực hiện:
      1. Mở phần cài đặt.
      2. Chọn thông báo.
    Hoàn tất thao tác.
~~~

Do có hai khoảng trắng nội dung trước `1.` và `2.`, ví dụ này khác với một đoạn văn chỉ gồm các dòng cùng mức thụt lề. Với hướng dẫn có định dạng cố định, `|` thường rõ ràng và ít gây bất ngờ hơn `>`.

## 5. Dấu -, dấu + và mặc định: xử lý cuối chuỗi

Dấu `|` hoặc `>` xác định **cách xử lý các dấu xuống dòng trong phần thân**. Một ký hiệu thứ hai, nếu có, xác định **các dấu xuống dòng ở cuối giá trị**. Đây là quy tắc *chomping*.

| Dạng | Tên quy tắc | Ý nghĩa |
| --- | --- | --- |
| `|` hoặc `>` | Clip, mặc định | Giữ một dấu xuống dòng cuối cùng; bỏ các dòng trống dư ở cuối. |
| `|-` hoặc `>-` | Strip | Bỏ dấu xuống dòng cuối cùng và các dòng trống dư ở cuối. |
| `|+` hoặc `>+` | Keep | Giữ dấu xuống dòng cuối cùng và cả các dòng trống dư ở cuối. |

**Chỉ khác nhau ở đoạn kết của chuỗi**. Chẳng hạn `|-` vẫn giữ dấu xuống dòng giữa các dòng nội dung, còn `>-` vẫn gộp các dòng thông thường thành một đoạn.

### So sánh cùng một nội dung

~~~yaml
clip: |
  A
  B

strip: |-
  A
  B

keep: |+
  A
  B

next: value
~~~

Các ký tự có hiệu lực được mô tả như sau:

| Khóa | Chuỗi biểu diễn | Giải thích |
| --- | --- | --- |
| `clip` | `"A\nB\n"` | Còn đúng một ký tự xuống dòng ở cuối. |
| `strip` | `"A\nB"` | Không có dấu xuống dòng cuối. |
| `keep` | `"A\nB\n\n"` | Có dấu xuống dòng cuối và thêm một dòng trống trước khóa tiếp theo. |

Trong ví dụ, dòng trống ngay trước `next` thuộc về khối `keep` và được giữ vì dấu `+`. Nếu bổ sung nhiều dòng trống cuối khối, `+` sẽ giữ thêm chúng.

Cách chọn thường gặp:

- Muốn chuỗi có cấu trúc nhiều dòng nhưng **không tự thêm newline cuối**: chọn `|-`.
- Muốn mô tả dài thành một đoạn văn liền mạch: chọn `>-`.
- Muốn văn bản nhiều dòng theo cách thông thường và có newline cuối: chọn `|`.
- Chỉ dùng `+` khi số dòng trống cuối chuỗi thực sự là yêu cầu của định dạng.

Đừng nhầm `|-` với việc “bỏ hết các dấu xuống dòng”; nó chỉ bỏ phần kết của giá trị.

## 6. Thụt lề: YAML dùng dấu cách để xác định phạm vi chuỗi

Chuỗi khối nằm bên dưới một khóa YAML. Phần nội dung phải được thụt lề sâu hơn khóa chứa nó:

~~~yaml
app:
  greeting: |-
    Xin chào,
    chúc bạn một ngày tốt lành.
  timeout: 10s
~~~

Hai dòng `Xin chào,` và `chúc bạn một ngày tốt lành.` thuộc giá trị `app.greeting`. Khóa `timeout` được đưa về cùng mức thụt lề với `greeting` nên **không nằm trong chuỗi**.

Bộ phân tích YAML nhận biết một mức thụt lề chung của khối và **loại mức đó** khỏi mỗi dòng của giá trị. Những dấu cách vượt quá mức chung vẫn thuộc về nội dung.

~~~yaml
app:
  message: |-
    Dòng bình thường
      Dòng được thụt vào hai dấu cách
    Dòng cuối
~~~

Giá trị tương ứng:

~~~text
"Dòng bình thường\n  Dòng được thụt vào hai dấu cách\nDòng cuối"
~~~

Dòng thứ hai có hai dấu cách **trong chuỗi thực sự**. Cần phân biệt chúng với bốn dấu cách chung của cả khối dùng để trình bày YAML.

### Chỉ báo thụt lề tường minh

Thông thường YAML tự suy ra mức thụt lề nội dung từ dòng không trống đầu tiên. Khi cần giữ dấu cách ở đầu dòng hoặc dòng đầu toàn khoảng trắng, có thể chỉ rõ mức thụt lề ngay sau `|` hoặc `>`:

~~~yaml
banner: |2-
    Dòng có hai dấu cách ở đầu.
    Dòng tiếp theo.
~~~

`2` chỉ định mức thụt lề khối là hai dấu cách tương đối so với khóa ở mức gốc. Trong ví dụ, mỗi dòng nội dung thụt vào bốn dấu cách; sau khi bỏ hai dấu cách của khối, giá trị vẫn giữ **hai dấu cách đầu mỗi dòng**.

Các cách viết như `|2-` và `|-2` đều thể hiện chỉ báo thụt lề kết hợp quy tắc *strip*. Tuy nhiên, đối với những cấu hình thông thường, hãy ưu tiên thụt lề nhất quán và chỉ dùng chỉ báo số khi thật sự cần bảo toàn khoảng trắng đầu dòng.

**Lưu ý:** YAML dùng dấu cách để thụt lề. Không dùng tab để thụt lề cấu trúc; tab có thể làm tệp không phân tích được. Khoảng trắng cuối dòng cũng có thể trở thành nội dung không mong muốn, nhất là khi xử lý chuỗi chính xác từng ký tự.

## 7. Dấu hai chấm, dấu # và những ký tự đặc biệt trong chuỗi khối

Bên trong một chuỗi `|` hoặc `>`, các ký tự như dấu hai chấm và dấu thăng thường được xem là **nội dung văn bản** nếu chúng nằm đúng phần thụt lề của khối:

~~~yaml
app:
  instructions: |-
    Lưu ý: không tắt ứng dụng.
    # Đây là một dòng nội dung, không phải comment YAML.
    Bước 1: lưu dữ liệu.
    Bước 2: đóng chương trình.
~~~

Dòng bắt đầu bằng `#` ở trên **vẫn thuộc chuỗi `app.instructions`**, bởi nó nằm bên trong nội dung chuỗi khối. Tương tự, dấu `:` trong câu không mở ra một khóa YAML mới.

Khi hết mức thụt lề của khối, YAML quay lại phân tích các khóa và giá trị theo cấu trúc thông thường. Vì vậy không thể tùy tiện đưa một dòng nội dung ra cùng mức với khóa cha.

Một chuỗi ký tự `\n` được gõ nguyên văn **bên trong** khối `|` hoặc `>` không phải ký hiệu yêu cầu xuống dòng; dấu gạch chéo ngược và chữ `n` là nội dung bình thường của block scalar. Hãy dùng các dòng vật lý và chọn `|`/`>` để biểu đạt ý định về xuống dòng.

## 8. Dùng chuỗi nhiều dòng trong application.yaml của Spring Boot

Giả sử ứng dụng cần lưu hai thuộc tính: mẫu thông báo cần giữ dòng và phần mô tả cần gộp dòng.

`src/main/resources/application.yaml`:

~~~yaml
app:
  notice: |-
    Xin chào,

    Yêu cầu của bạn đã được tiếp nhận.
    Chúng tôi sẽ liên hệ trong 24 giờ.

    Trân trọng,
    Bộ phận hỗ trợ

  description: >-
    Dịch vụ tiếp nhận yêu cầu hỗ trợ,
    kiểm tra các thông tin cần thiết
    và chuyển yêu cầu đến bộ phận phụ trách.
~~~

Sau khi Spring Boot nạp Config Data, các khóa `app.notice` và `app.description` trở thành giá trị chuỗi mà ứng dụng có thể truy cập qua `Environment`.

### 8.1. Đọc trực tiếp bằng Environment

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class NoticeService {
    private final Environment environment;

    public NoticeService(Environment environment) {
        this.environment = environment;
    }

    public String notice() {
        return environment.getRequiredProperty("app.notice");
    }

    public String description() {
        return environment.getRequiredProperty("app.description");
    }
}
~~~

`notice()` trả về chuỗi giữ các dấu xuống dòng và dòng trống trong mẫu thông báo; `description()` trả về một đoạn văn liền mạch. Vì cả hai dùng dấu `-`, không có newline cuối chuỗi.

### 8.2. Gắn nhiều thuộc tính bằng @ConfigurationProperties

Khi có cả nhóm thuộc tính liên quan, có thể dùng một record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppTextProperties(
        String notice,
        String description) {
}
~~~

Đăng ký record bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(AppTextProperties.class)` trong cấu hình. Sau đó Spring Boot gắn cả hai khóa vào các trường `String` tương ứng.

~~~java
import org.springframework.stereotype.Service;

@Service
public class MessageService {
    private final AppTextProperties properties;

    public MessageService(AppTextProperties properties) {
        this.properties = properties;
    }

    public String composeNotice() {
        return properties.notice();
    }
}
~~~

Kiểu trả về vẫn là `String`; cú pháp `|` và `>` chỉ tham gia khi **phân tích tệp YAML**, không xuất hiện như ký hiệu đặc biệt trong Java.

### 8.3. Dùng @Value cho một khóa

Cũng có thể đọc riêng một thuộc tính:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class NoticeTemplate {
    private final String text;

    NoticeTemplate(@Value("${app.notice}") String text) {
        this.text = text;
    }

    public String text() {
        return text;
    }
}
~~~

`@Value` nhận chuỗi đã được phân giải từ `Environment`. Nếu giá trị có dấu xuống dòng thật, Java tiếp tục giữ chúng. Spring không tự chèn hoặc xóa dấu xuống dòng chỉ vì sử dụng `@Value` thay cho `@ConfigurationProperties`.

## 9. Phân biệt cách trình bày YAML với giá trị mà ứng dụng sử dụng

Giả sử hai tệp cấu hình chứa các cách viết khác nhau:

~~~yaml
first: |-
  Dòng một
  Dòng hai

second: >-
  Dòng một
  Dòng hai
~~~

Khi ứng dụng nối, so sánh, gửi qua HTTP hoặc hiển thị chúng, dấu xuống dòng có thể ảnh hưởng kết quả:

~~~java
String first = environment.getRequiredProperty("first");
String second = environment.getRequiredProperty("second");

System.out.println(first.equals(second)); // false
System.out.println(first.contains("\n"));  // true
System.out.println(second.contains("\n")); // false
~~~

`first` chứa `"Dòng một\nDòng hai"`; `second` chứa `"Dòng một Dòng hai"`. Hai giá trị khác nhau mặc dù cả hai được trình bày trên hai dòng YAML.

Với văn bản để người đọc xem, sự khác biệt này có thể chỉ là cách hiển thị. Với chuỗi được dùng để ký điện tử, tính checksum, đối chiếu chữ ký, so khớp chính xác hoặc truyền tới hệ thống yêu cầu định dạng cố định, khác một dấu xuống dòng cũng có thể khiến kết quả sai.

Cũng cần nhớ rằng chuỗi chỉ giữ ý nghĩa sau khi YAML được phân tích. Nếu cùng thuộc tính còn tồn tại trong biến môi trường hoặc tham số dòng lệnh có độ ưu tiên cao hơn, giá trị ứng dụng nhận sẽ được xác định theo thứ tự nguồn của Spring Boot. `|`/`>` không làm thay đổi độ ưu tiên đó.

## 10. Các tình huống dễ dùng sai

### 10.1. Dùng > cho văn bản cần giữ nguyên dòng

~~~yaml
script: >-
  echo start
  echo done
~~~

Chuỗi có hiệu lực là `"echo start echo done"`, không phải hai câu lệnh riêng. Nếu hệ thống nhận yêu cầu mỗi câu lệnh một dòng, hãy dùng `|-`.

### 10.2. Dùng | cho đoạn mô tả chỉ ngắt dòng để dễ đọc

~~~yaml
description: |-
  Đây là một mô tả dài
  được chia dòng cho dễ nhìn.
~~~

Giá trị giữ newline ở giữa, trong khi mã Java có thể cần một đoạn văn liên tục. Với mục đích đó, `>-` phù hợp hơn.

### 10.3. Quên newline cuối chuỗi

~~~yaml
payload: |
  READY
~~~

Giá trị là `"READY\n"`, không phải `"READY"`. Nếu giao thức bên ngoài yêu cầu khớp chính xác `READY`, dùng `|-`.

### 10.4. Coi mọi dòng trống trong > là dấu cách

Dòng trống tạo ranh giới đoạn nên `>` không phải phép thay thế mọi newline bằng dấu cách. Khi văn bản có nhiều đoạn hoặc dòng thụt lề sâu hơn, việc gộp có ngoại lệ. Nếu cần kiểm soát từng dấu xuống dòng, chọn `|` sẽ dễ dự đoán hơn.

### 10.5. Thụt lề nội dung sai mức

~~~yaml
app:
  message: |-
    Dòng hợp lệ
  Dòng sai mức
~~~

Dòng `Dòng sai mức` không thuộc chuỗi `app.message`. Vì nó không có cấu trúc khóa–giá trị hợp lệ ở vị trí đó, ví dụ sẽ làm YAML lỗi cú pháp. Kiểm tra vị trí dấu cách, tránh tab và để nội dung sâu hơn khóa `message`.

### 10.6. Nhầm escape với newline thật

~~~yaml
app:
  text: |-
    Dòng một\nDòng hai
~~~

Nội dung ở đây chỉ có **một dòng vật lý** và chứa hai ký tự `\`, `n` ở giữa. Nó không giống:

~~~yaml
app:
  text: |-
    Dòng một
    Dòng hai
~~~

Ví dụ thứ hai mới có dấu xuống dòng thật giữa hai phần văn bản.

### 10.7. Nghĩ YAML tự bảo vệ dữ liệu nhạy cảm

Block scalar giúp biểu diễn chuỗi nhiều dòng; nó không mã hóa thông tin và không thay thế cơ chế quản lý bí mật. Không ghi khóa bí mật hoặc nội dung nhạy cảm vào `application.yaml` được đưa lên repository công khai. Giá trị nhiều dòng như chứng chỉ hoặc khóa mật mã còn có thể đòi hỏi định dạng newline chính xác, nên cần đọc tài liệu của hệ thống cung cấp bí mật và hệ thống tiêu thụ.

## 11. Cách kiểm tra giá trị thật khi gặp lỗi

Khi nội dung hiển thị sai, nhiều khi mắt thường không phân biệt được dấu cách, newline hoặc ký tự cuối chuỗi. Trong môi trường phát triển, hãy kiểm tra chuỗi đã được nạp từ `Environment`:

~~~java
String value = environment.getRequiredProperty("app.notice");

System.out.println("Length = " + value.length());
System.out.println(
    value.replace("\r", "\\r")
         .replace("\n", "\\n\n")
);
~~~

Đoạn này hiển thị ký hiệu `\r`/`\n` để quan sát ký tự xuống dòng. Với dữ liệu nhạy cảm, **không in giá trị ra log**; chỉ dùng những chuỗi mẫu vô hại khi thực hành.

Nếu giá trị vẫn khác kỳ vọng, kiểm tra tuần tự: tệp YAML đang được nạp có đúng không; khóa có bị nguồn cấu hình ưu tiên cao ghi đè không; đã chọn `|` hay `>`; có dấu `-`/`+` không; mức thụt lề và dòng trống cuối khối có đúng không. Đây là các nguyên nhân phổ biến nhất.

## 12. Bài thực hành

### Bài 1 — dự đoán chuỗi nhận được

~~~yaml
a: |-
  Xin
  chào
b: >-
  Xin
  chào
c: |
  Xin
  chào
~~~

Hãy biểu diễn mỗi kết quả bằng `\n`:

- `a` có dấu xuống dòng giữa hai từ và không có newline cuối.
- `b` có dấu cách giữa hai từ và không có newline cuối.
- `c` có dấu xuống dòng giữa hai từ và một newline cuối.

Đáp án:

~~~text
a = "Xin\nchào"
b = "Xin chào"
c = "Xin\nchào\n"
~~~

### Bài 2 — sửa cú pháp cho đúng ý định

Ứng dụng cần gửi email như sau:

~~~text
Xin chào,

Yêu cầu của bạn đã hoàn tất.
Cảm ơn bạn.
~~~

Hãy tạo `mail.body` với dấu xuống dòng đúng như văn bản ở trên, không thêm newline cuối. Đáp án:

~~~yaml
mail:
  body: |-
    Xin chào,

    Yêu cầu của bạn đã hoàn tất.
    Cảm ơn bạn.
~~~

### Bài 3 — giảm số dòng vật lý mà không đổi thành nhiều dòng trong Java

Cho đoạn mô tả gồm ba câu, muốn trải nội dung qua nhiều dòng tệp cho dễ đọc nhưng khi lấy ra chỉ có **một dòng**:

~~~yaml
app:
  description: >-
    Hệ thống kiểm tra yêu cầu.
    Sau đó dữ liệu được lưu.
    Cuối cùng kết quả được trả về.
~~~

Kiểm tra bằng `Environment.getProperty("app.description")`. Kết quả là một chuỗi có các câu ngăn nhau bằng dấu cách, không chứa newline bên trong hay ở cuối.

### Bài 4 — thử ảnh hưởng của dấu +

Viết một chuỗi `|+` có thêm hai dòng trống trước khóa kế tiếp, sau đó so sánh độ dài với `|` và `|-` cùng phần nội dung. Chú ý số ký tự newline được giữ ở cuối. Quan sát giá trị thực tế để phân biệt *clip*, *strip* và *keep*.

## 13. Bảng ghi nhớ để lựa chọn

| Mục đích | Cú pháp nên cân nhắc | Điều cần nhớ |
| --- | --- | --- |
| Giữ newline giữa các dòng và giữ một newline cuối | `|` | Phù hợp văn bản nhiều dòng thông thường. |
| Giữ newline bên trong nhưng không có newline cuối | `|-` | Dễ dùng cho email template, banner, chuỗi cần so khớp chính xác. |
| Gộp dòng vật lý thành một đoạn văn, giữ newline cuối | `>` | Các dòng trống và dòng thụt lề sâu có quy tắc riêng. |
| Gộp dòng và loại newline cuối | `>-` | Phù hợp mô tả dài viết qua nhiều dòng YAML. |
| Giữ cả các dòng trống ở cuối | `|+` hoặc `>+` | Chỉ dùng khi phần đuôi trắng có ý nghĩa. |
| Nội dung có dấu cách ở đầu dòng cần bảo toàn | `|2-` hoặc chỉ báo thụt lề tương ứng | Kiểm tra mức thụt lề chung và dấu cách còn lại. |

**Quy tắc nhớ nhanh:** `|` giữ dòng, `>` gộp dòng; `-` bỏ newline cuối, `+` giữ các dòng trống cuối, còn không ghi gì thì giữ một newline cuối theo mặc định. Spring Boot đọc **giá trị chuỗi sau khi YAML được phân tích**; cú pháp block scalar chỉ quyết định cách giá trị ấy được tạo ra.

**Tài liệu tham khảo:**
- [YAML 1.2.2 — Block Scalar Styles](https://yaml.org/spec/1.2.2/#81-block-scalar-styles).
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).