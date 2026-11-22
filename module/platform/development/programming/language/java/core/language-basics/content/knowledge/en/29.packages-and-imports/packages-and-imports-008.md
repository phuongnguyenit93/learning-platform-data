# Xử lý hai lớp trùng tên và giới hạn của `import` trong Java

## 1. Vì sao hai lớp có thể trùng tên?

Trong Java, **tên đơn giản** (*simple name*) là phần cuối của tên lớp, chẳng hạn `Result`. **Tên đầy đủ** (*fully qualified name*) gắn tên package với tên kiểu, chẳng hạn `com.example.payment.Result` và `com.example.network.Result`.

Hai lớp cùng tên đơn giản có thể tồn tại trong hai package khác nhau. Vấn đề chỉ xuất hiện khi mã nguồn cần phân giải tên ngắn `Result` nhưng có nhiều ứng viên. `import` giúp sử dụng tên ngắn của kiểu có thể truy cập; nó **không đổi tên lớp, không tạo alias, không sao chép mã**, cũng không bắt JVM nạp lớp ngay tại thời điểm viết import.

Ví dụ các kiểu hợp lệ và khác nhau:

```text
com.example.payment.Result
com.example.network.Result
java.util.Date
java.sql.Date
```

Khi gặp trùng tên, cách chắc chắn nhất là dùng **tên đầy đủ** tại nơi sử dụng.

## 2. Phân biệt xung đột từ import cụ thể và import theo yêu cầu

~~~java
package com.example.app;
import java.util.List;            // Import một kiểu
import java.util.*;               // Import nhiều kiểu theo yêu cầu
import static java.lang.Math.PI;  // Import thành viên static
~~~

Các khai báo import chỉ giúp **phân giải tên trong source**, không tạo alias, không vượt qua quyền truy cập và không làm Java nạp lớp lúc chạy. Dấu `*` không tự bao gồm package con.

Bài này tập trung vào khác biệt giữa **hai single-type imports** cho hai kiểu khác nhau cùng simple name (lỗi tại dòng import) và **hai wildcard imports** cung cấp hai ứng viên cùng tên (mơ hồ khi dùng tên đó). Để dùng cả hai kiểu, hãy import cụ thể tối đa một kiểu rồi viết qualified name cho kiểu còn lại, hoặc viết qualified name cho cả hai.

## 3. Ví dụ chạy được: hai lớp Result khác package

Tạo cấu trúc thư mục:

```text
src/
└── com/
    └── example/
        ├── payment/
        │   └── Result.java
        ├── network/
        │   └── Result.java
        └── app/
            └── Main.java
```

**Tệp `src/com/example/payment/Result.java`:**

```java
package com.example.payment;

public class Result {
    public String origin() {
        return "payment";
    }
}
```

**Tệp `src/com/example/network/Result.java`:**

```java
package com.example.network;

public class Result {
    public String origin() {
        return "network";
    }
}
```

**Tệp `src/com/example/app/Main.java`:**

```java
package com.example.app;

import com.example.payment.Result;
import com.example.network.*;

public class Main {
    public static void main(String[] args) {
        Result payment = new Result();
        com.example.network.Result network = new com.example.network.Result();

        System.out.println("simple=" + payment.origin());
        System.out.println("qualified=" + network.origin());
    }
}
```

Ở đây, `import com.example.payment.Result;` đưa **một kiểu cụ thể** vào phạm vi tên ngắn. `import com.example.network.*;` chỉ nhập theo nhu cầu, nên `Result` không trở thành mơ hồ: khai báo import một kiểu cụ thể được ưu tiên hơn import theo nhu cầu. Lớp `network.Result` vẫn được dùng bình thường khi ghi tên đầy đủ. Nếu chỉ dùng tên đầy đủ cho kiểu network, có thể bỏ hẳn `import com.example.network.*;`.

**Biên dịch và chạy với JDK 17+** tại thư mục có `src` (các đường dẫn dùng `/` được Java chấp nhận trên Windows, Linux và macOS). Tạo thư mục `out` một lần bằng `mkdir out`, sau đó:

```sh
javac -encoding UTF-8 -d out src/com/example/payment/Result.java src/com/example/network/Result.java src/com/example/app/Main.java
java -cp out com.example.app.Main
```

Kết quả của lệnh `java`, chính xác:

```text
simple=payment
qualified=network
```

Tên dùng trong `java -cp out com.example.app.Main` là **tên đầy đủ của lớp chứa `main`**. `-d out` đặt các file `.class` vào thư mục tương ứng với package. Việc import không thay thế biên dịch lớp phụ thuộc hoặc cấu hình classpath.

## 4. Những trường hợp trùng tên và cách Java xử lý

| Tình huống | Dùng tên ngắn `Result` | Cách xử lý |
| --- | --- | --- |
| `import com.example.payment.Result;` cùng `import com.example.network.*;` | Chọn kiểu `payment.Result` vì import tường minh | Ghi `com.example.network.Result` khi cần kiểu còn lại |
| `import com.example.payment.*;` và `import com.example.network.*;` | **Mơ hồ** nếu tham chiếu `Result` khi cả hai kiểu cùng truy cập được | Chọn một import tường minh hoặc dùng tên đầy đủ |
| Hai `import` tường minh cho **hai kiểu khác nhau** cùng tên đơn giản | **Lỗi biên dịch ngay tại các khai báo import** | Giữ tối đa một import tường minh cho tên đó |
| Kiểu cùng package và kiểu từ wildcard ở package khác cùng tên | Kiểu cùng package được chọn trước kiểu chỉ đến từ import theo nhu cầu | Ghi tên đầy đủ cho kiểu thuộc package khác |
| Kiểu thành viên/lớp lồng nhau hay tên kiểu được khai báo tại phạm vi gần | Có thể che khuất tên được import tùy vị trí và loại khai báo | Kiểm tra phạm vi hoặc dùng tên kiểu đủ rõ ràng |

### 4.1. Hai import tường minh: lỗi dù chưa tạo đối tượng

Ví dụ sau **cố ý không biên dịch được**, với giả định hai `Result` trong ví dụ trên đều tồn tại:

```java
package com.example.app;

import com.example.payment.Result;
import com.example.network.Result; // lỗi: hai single-type-import khác kiểu, cùng tên đơn giản

public class InvalidImports {
}
```

Đây là xung đột tại *khai báo import*, không phải đợi đến khi gọi `new Result()`. Cần xóa một import và dùng tên đầy đủ tại chỗ cần kiểu thứ hai.

### 4.2. Hai wildcard: lỗi chỉ khi tên ngắn bị mơ hồ

Đoạn sau cũng **cố ý không biên dịch được**:

```java
package com.example.app;

import com.example.payment.*;
import com.example.network.*;

public class AmbiguousUse {
    Result value = new Result(); // cả hai package đều có Result
}
```

Hai khai báo wildcard tự chúng được phép tồn tại. Lỗi phát sinh ở tham chiếu `Result` vì cả hai kiểu cùng phù hợp. Nếu đổi thành `com.example.payment.Result value = new com.example.payment.Result();` thì không còn mơ hồ.

### 4.3. Ví dụ thực tế: java.util.Date và java.sql.Date

`java.util.Date` và `java.sql.Date` là hai kiểu khác nhau, dù cùng tên đơn giản. Có thể viết:

```java
import java.util.Date;

class Example {
    Date utilDate;
    java.sql.Date sqlDate;
}
```

Đây là đoạn minh họa khai báo kiểu, không phải chương trình có `main`. Không thể import cả `java.util.Date` và `java.sql.Date` bằng hai dòng single-type-import rồi kỳ vọng trình biên dịch tự phân biệt theo ý nghĩa nghiệp vụ. Trong code mới, khi biểu diễn ngày không kèm thời gian, thường nên cân nhắc `java.time.LocalDate`; `java.sql.Date` vẫn có vai trò trong API JDBC.

## 5. Phạm vi ưu tiên tên: cần lưu ý điều gì?

Có thể dùng quy tắc thực hành sau để đọc mã:

1. **Tìm tên đã được khai báo trong phạm vi gần** (ví dụ kiểu thành viên, tham số kiểu), vì có thể che khuất các tên đến từ import.
2. **Kiểm tra import một kiểu cụ thể**, như `import pkg1.Result;`, trước các import theo nhu cầu.
3. **Các kiểu trong package hiện tại** không cần import và được ưu tiên so với kiểu chỉ có từ wildcard ở package khác.
4. **Các import theo nhu cầu** và `java.lang` cung cấp ứng viên khi chưa có khai báo gần hơn; nếu nhiều kiểu cùng tên vẫn phù hợp thì tham chiếu tên ngắn có thể mơ hồ.
5. Khi không chắc, dùng **tên đầy đủ**. Cần lưu ý đây là hướng dẫn thực hành; quy tắc chính xác của ngôn ngữ còn phụ thuộc loại tên, vị trí khai báo và shadowing.

Đặc biệt, một **single-type-import** có thể che khuất kiểu cùng tên được khai báo ở **tệp khác của cùng package**, trong khi khai báo một kiểu top-level cùng tên **ngay trong cùng tệp biên dịch** với single-type-import đó là tình huống xung đột. Vì vậy đừng dựa vào nhận định tuyệt đối rằng “cùng package luôn thắng mọi import”.

## 6. Những giới hạn khác của import

**(a) Import không mở quyền truy cập.** Một kiểu top-level `public` ở package khác có thể được import khi package đó khả dụng. Kiểu top-level không có `public` chỉ được truy cập từ package của nó; thêm `import` không biến nó thành `public`. Thành viên `private`, `protected`, package-private vẫn tuân theo quy tắc truy cập riêng. Có thể import được tên lớp nhưng vẫn không được gọi constructor hoặc method không phù hợp quyền truy cập.

**(b) Package con là package riêng.** `com.example` và `com.example.internal` không có quan hệ “kế thừa” quyền truy cập mặc định. `import com.example.*;` không nhập `com.example.internal.Helper`.

**(c) Import không thay thế classpath hay module path.** Nếu thư viện không nằm trên đường biên dịch, lỗi không thể giải quyết chỉ bằng thêm import. Trong dự án dùng Java Platform Module System, module phải cho phép đọc module chứa kiểu và package liên quan phải được export theo luật module; import không tự thêm `requires` hay `exports`.

**(d) Không import kiểu từ unnamed package vào named package.** Nếu một tệp có `package com.example.app;`, nó không thể dùng import để truy cập lớp nằm trong unnamed/default package. Nên tổ chức các lớp thành named package rõ ràng.

**(e) Import không kế thừa qua các tệp.** Import khai báo trong `Main.java` chỉ có hiệu lực trong đơn vị biên dịch đó; `Another.java` phải tự khai báo import cần thiết. Một import không làm chương trình chạy nhanh hơn hay chậm hơn theo cách có ý nghĩa chỉ do đổi tên ngắn thành tên đầy đủ.

**(f) Import kiểu khác static import.** `import java.lang.Math;` cho phép dùng tên kiểu `Math` nhưng vẫn phải viết `Math.PI`. `import static java.lang.Math.PI;` cho phép tham chiếu `PI` trực tiếp. Static import cũng có quy tắc xung đột tên và khả năng truy cập riêng; nó không giải quyết việc hai lớp top-level khác package có cùng tên.

## 7. Cách xử lý khi gặp lỗi trong dự án

Nếu `javac` báo tên kiểu *ambiguous*, xem những import `*` nào đưa các kiểu cùng tên vào; thay bằng một import cụ thể hoặc dùng tên đầy đủ. Nếu báo xung đột tại dòng `import`, kiểm tra hai import cụ thể cùng tên đơn giản; xóa một dòng. Nếu báo `cannot find symbol` hoặc `package ... does not exist`, kiểm tra chính tả package/class, vị trí source, JAR, classpath hoặc module path trước khi sửa import. Nếu báo kiểu không truy cập được, cần kiểm tra `public`/phạm vi package/module chứ không thêm wildcard.

Trong IDE, chức năng **Organize Imports** có thể bỏ import thừa và chọn kiểu phù hợp, nhưng vẫn nên đọc lại vì IDE không thể tự quyết định lớp nào đúng về mặt nghiệp vụ. Đối với tên phổ biến như `Date`, `List`, `Logger`, `Result`, `Exception`, dùng tên đầy đủ ở vài dòng thường rõ hơn đặt hai bộ import wildcard.

## 8. Ghi nhớ và tự kiểm tra

- Hai lớp `a.Result` và `b.Result` có được tồn tại đồng thời không? **Có**, vì tên đầy đủ khác nhau.
- Hai single-type-import `a.Result` và `b.Result` có cùng nằm trong một tệp Java được không? **Không**, nếu đó là hai kiểu khác nhau.
- Hai wildcard `a.*` và `b.*` có được khai báo cùng nhau không? **Có**; nhưng `Result` bằng tên ngắn sẽ mơ hồ khi cả hai lớp tương ứng đều có thể truy cập.
- `import a.*;` có nhập `a.sub.Helper` không? **Không**.
- `import a.Secret;` có làm lớp package-private `Secret` trở thành công khai không? **Không**.
- Muốn dùng hai kiểu cùng tên trong một tệp, nên viết thế nào? **Import tường minh tối đa một kiểu cùng tên và dùng fully qualified name cho kiểu còn lại**, hoặc viết fully qualified name cho cả hai.

**Quy tắc hữu ích nhất:** import chỉ giảm số lần phải gõ tên package; **tên đầy đủ, khả năng truy cập và cấu hình biên dịch** mới quyết định kiểu nào thực sự được tham chiếu.
