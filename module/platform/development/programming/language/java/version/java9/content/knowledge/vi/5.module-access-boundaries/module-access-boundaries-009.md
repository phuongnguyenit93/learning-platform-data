# Giới hạn phạm vi --add-exports hoặc --add-opens khi tích hợp

JPMS đóng gói các package trong named module. Một kiểu có modifier **public** vẫn có thể không truy cập được từ mô-đun khác nếu package chứa kiểu đó chưa được export. Tương tự, một framework có thể nhìn thấy kiểu public nhưng vẫn không được phép dùng reflection để truy cập trường hoặc phương thức private nếu package chưa được mở.

Khi tích hợp một thư viện hoặc framework chưa thể sửa module descriptor, Java cung cấp hai tùy chọn dòng lệnh để cấp quyền truy cập có phạm vi rõ ràng:

- **--add-exports** bổ sung quyền truy cập thông thường vào một package cho mô-đun đích.
- **--add-opens** mở một package cho deep reflection từ mô-đun đích tại thời điểm chạy.

Hai tùy chọn này giải quyết hai loại truy cập khác nhau. Chọn đúng loại, đúng package và đúng mô-đun đích giúp ứng dụng tương thích với thư viện cần tích hợp mà vẫn giữ ranh giới JPMS ở phạm vi nhỏ nhất.

## 1. Cú pháp và phạm vi áp dụng

Cả hai tùy chọn đều chỉ rõ mô-đun nguồn, package cần cấp quyền và mô-đun nhận quyền:

~~~text
--add-exports <source-module>/<package>=<target-module>
--add-opens   <source-module>/<package>=<target-module>
~~~

Ví dụ:

~~~bash
--add-exports com.example.lib/com.example.internal=com.example.app
--add-opens com.example.lib/com.example.model=com.example.orm
~~~

Trong đó:

- **source-module** là tên mô-đun đang sở hữu package.
- **package** là tên package đầy đủ, không phải tên lớp.
- **target-module** là mô-đun được cấp quyền truy cập.

Có thể chỉ định nhiều mô-đun đích bằng cách phân tách tên bằng dấu phẩy. Nếu mã cần quyền truy cập thuộc classpath và unnamed module, có thể dùng **ALL-UNNAMED** làm mô-đun đích:

~~~bash
--add-opens com.example.lib/com.example.model=ALL-UNNAMED
~~~

**ALL-UNNAMED** áp dụng cho các unnamed module, thường là mã được nạp từ classpath. Đây là giá trị đặc biệt ở phía mô-đun đích; không dùng nó thay cho tên mô-đun nguồn.

Tên mô-đun và package phải khớp chính xác với module descriptor. Tùy chọn cấp quyền cho một package cụ thể; nó không tự mở mọi package con. Nếu framework cần nhiều package, hãy khai báo từng package cần thiết.

## 2. --add-exports: cấp quyền truy cập thông thường

**--add-exports** bổ sung một qualified export từ mô-đun nguồn tới mô-đun đích. Nó cho phép mã của mô-đun đích truy cập các kiểu và thành viên public trong package được chỉ định, theo quy tắc truy cập Java thông thường.

Giả sử mô-đun **com.example.lib** có cấu trúc:

~~~java
module com.example.lib {
    exports com.example.publicapi;
}
~~~

Package **com.example.internal** tồn tại nhưng không được export:

~~~java
package com.example.internal;

public final class InternalApi {
    private InternalApi() { }

    public static String message() {
        return "internal-access=ok";
    }
}
~~~

Mô-đun ứng dụng khai báo:

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

Nếu mã nguồn ứng dụng import **com.example.internal.InternalApi**, trình biên dịch sẽ báo package không được export. Có thể cấp quyền ở bước biên dịch bằng:

~~~bash
javac -d out --module-source-path src ^
  --add-exports com.example.lib/com.example.internal=com.example.app ^
  -m com.example.lib,com.example.app
~~~

Vì quyền truy cập mô-đun cũng được kiểm tra lúc chạy, lệnh **java** cần nhận tùy chọn tương ứng:

~~~bash
java --module-path out ^
  --add-exports com.example.lib/com.example.internal=com.example.app ^
  -m com.example.app/com.example.app.Main
~~~

Trong các ví dụ trên, dấu **^** là ký tự nối dòng của Windows Command Prompt. Nếu chạy trong Bash hoặc shell không dùng cú pháp đó, viết toàn bộ lệnh trên một dòng hoặc dùng ký tự nối dòng tương ứng của shell.

### 2.1. Khi nào cần --add-exports?

Dùng tùy chọn này khi mã nguồn hoặc bytecode của mô-đun đích cần truy cập kiểu public thuộc package chưa được mô-đun nguồn export cho nó. Ví dụ:

- Một thư viện cũ đặt API cần tích hợp trong package nội bộ chưa export.
- Một ứng dụng phải gọi kiểu public trong package mà nhà cung cấp chưa công khai cho mô-đun ứng dụng.
- Một công cụ kiểm thử cần truy cập API public trong package được giữ kín khi chạy production.

**--add-exports không cấp quyền truy cập private hoặc package-private.** Các modifier truy cập của ngôn ngữ Java vẫn có hiệu lực. Tùy chọn này cũng không tự cấp quyền deep reflection.

### 2.2. --add-exports dùng với javac và java

Nếu mã nguồn tham chiếu package chưa export, cần cấp quyền cho **javac** để biên dịch. Khi chạy ứng dụng, cần cấp quyền tương ứng cho **java**.

Chỉ thêm tùy chọn ở bước biên dịch không có nghĩa là mô-đun đã được export khi chạy. Nếu thiếu tùy chọn runtime, ứng dụng có thể gặp **IllegalAccessError** khi thực thi lệnh truy cập lớp hoặc thành viên của package đó.

## 3. --add-opens: cấp quyền deep reflection

**--add-opens** mở package của mô-đun nguồn cho reflection sâu từ mô-đun đích tại thời điểm chạy. Nó cho phép các API reflection truy cập những thành viên không public khi các điều kiện truy cập khác được đáp ứng.

Ví dụ, package **com.example.publicapi** đã được export và có một lớp public chứa trường private:

~~~java
package com.example.publicapi;

public final class RecordView {
    private final String secret = "classified";
}
~~~

Ứng dụng có thể biên dịch vì package đã được export. Tuy nhiên, nếu ứng dụng hoặc framework gọi:

~~~java
Field field = RecordView.class.getDeclaredField("secret");
field.setAccessible(true);
~~~

thì việc truy cập sâu có thể bị từ chối nếu package chưa mở cho mô-đun ứng dụng. Lỗi thường gặp là **InaccessibleObjectException**.

Có thể mở riêng package cho mô-đun ứng dụng bằng:

~~~bash
java --module-path out ^
  --add-opens com.example.lib/com.example.publicapi=com.example.app ^
  -m com.example.app/com.example.app.Main
~~~

Tùy chọn **--add-opens** được áp dụng ở runtime. Nó không làm cho package trở nên có thể import khi biên dịch. Nếu mã nguồn cần tham chiếu trực tiếp một kiểu public trong package chưa export, vẫn cần xử lý quyền export riêng.

### 3.1. Khi nào cần --add-opens?

Thường gặp khi tích hợp:

- ORM hoặc thư viện ánh xạ đối tượng cần đọc/ghi trường private.
- Dependency injection framework cần tạo hoặc gán giá trị qua reflection.
- Framework serialization cần truy cập trạng thái nội bộ của đối tượng.
- Công cụ kiểm thử cần kiểm tra thành viên không public trong một package cụ thể.

Chỉ mở package mà framework thực sự cần. Nếu framework chỉ cần gọi phương thức public, hãy kiểm tra xem **exports** đã đủ hay chưa trước khi cấp thêm quyền deep reflection.

## 4. Phân biệt hai tùy chọn

| Tiêu chí | --add-exports | --add-opens |
|---|---|---|
| Mục đích | Truy cập thông thường vào package | Deep reflection vào package |
| Trường hợp chính | Import/gọi kiểu và thành viên public | Reflection vào thành viên không public |
| Dùng ở bước biên dịch javac | Có | Không |
| Dùng ở runtime java | Có | Có |
| Cấp quyền private qua reflection | Không | Có, theo quy tắc reflection |
| Thay đổi module-info.class | Không | Không |
| Phạm vi | Một package và mô-đun đích | Một package và mô-đun đích |

Hãy xác định loại lỗi trước khi chọn:

- **package is not visible** hoặc lỗi truy cập kiểu public trong package chưa export: xem xét **--add-exports**.
- **InaccessibleObjectException** khi framework gọi **setAccessible** hoặc truy cập thành viên private: xem xét **--add-opens**.
- **IllegalAccessError** lúc chạy sau khi biên dịch bằng **--add-exports**: kiểm tra xem tùy chọn export đã được truyền vào đúng tiến trình JVM hay chưa.

Một package có thể vừa cần export vừa cần open. Ví dụ ứng dụng gọi API public của package và ORM cần reflection sâu vào cùng package. Khi đó, hai quyền có thể được cấp riêng cho đúng mô-đun đích.

## 5. Ví dụ hoàn chỉnh: tích hợp một thư viện có package nội bộ

Ví dụ sau minh họa đồng thời hai trường hợp: ứng dụng gọi một kiểu public trong package chưa export và dùng reflection để đọc trường private trong package đã export.

Cấu trúc:

~~~text
src/
├── com.example.lib/
│   ├── module-info.java
│   ├── com/example/publicapi/RecordView.java
│   └── com/example/internal/InternalApi.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 5.1. Mô-đun thư viện

Tệp **src/com.example.lib/module-info.java**:

~~~java
module com.example.lib {
    exports com.example.publicapi;
}
~~~

Tệp **src/com.example.lib/com/example/publicapi/RecordView.java**:

~~~java
package com.example.publicapi;

public final class RecordView {
    private final String secret = "classified";
}
~~~

Tệp **src/com.example.lib/com/example/internal/InternalApi.java**:

~~~java
package com.example.internal;

public final class InternalApi {
    private InternalApi() { }

    public static String message() {
        return "exported-access=ok";
    }
}
~~~

Mô-đun chỉ export **com.example.publicapi**. Package **com.example.internal** vẫn nằm trong mô-đun và chưa được export.

### 5.2. Mô-đun ứng dụng

Tệp **src/com.example.app/module-info.java**:

~~~java
module com.example.app {
    requires com.example.lib;
}
~~~

Tệp **src/com.example.app/com/example/app/Main.java**:

~~~java
package com.example.app;

import java.lang.reflect.Field;
import com.example.internal.InternalApi;
import com.example.publicapi.RecordView;

public final class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(InternalApi.message());

        Field secret = RecordView.class.getDeclaredField("secret");
        secret.setAccessible(true);
        System.out.println("reflective-secret=" + secret.get(new RecordView()));
    }
}
~~~

Ứng dụng gọi trực tiếp **InternalApi.message()**, vì vậy package internal cần được export cho **com.example.app**. Ứng dụng cũng dùng reflection để đọc trường private **secret**, vì vậy package publicapi cần được mở cho deep reflection.

### 5.3. Biên dịch và chạy

Biên dịch với quyền export có phạm vi cụ thể:

~~~bash
javac -d out --module-source-path src ^
  --add-exports com.example.lib/com.example.internal=com.example.app ^
  -m com.example.lib,com.example.app
~~~

Chạy với cả quyền export và open:

~~~bash
java --module-path out ^
  --add-exports com.example.lib/com.example.internal=com.example.app ^
  --add-opens com.example.lib/com.example.publicapi=com.example.app ^
  -m com.example.app/com.example.app.Main
~~~

Kết quả stdout:

~~~text
exported-access=ok
reflective-secret=classified
~~~

Hai tùy chọn giải quyết hai quyền riêng biệt:

- **--add-exports** cho phép ứng dụng gọi API public thuộc package **com.example.internal**.
- **--add-opens** cho phép reflection của ứng dụng truy cập trường private trong **com.example.publicapi**.

Nếu bỏ **--add-exports** khỏi lệnh biên dịch, compiler báo package **com.example.internal** không được export. Nếu biên dịch thành công nhưng bỏ tùy chọn export khi chạy, ứng dụng có thể gặp **IllegalAccessError**. Nếu vẫn giữ export nhưng bỏ **--add-opens**, phần reflection sâu có thể gặp **InaccessibleObjectException**.

## 6. Giới hạn và cách chọn phạm vi an toàn

### 6.1. Quyền được cấp không thay đổi module descriptor

Các tùy chọn dòng lệnh chỉ thay đổi module graph của tiến trình được khởi chạy. Chúng không sửa **module-info.java**, không ghi thay đổi vào **module-info.class** và không biến package thành API công khai lâu dài của thư viện.

Khi ứng dụng được khởi chạy lại, phải truyền lại các tùy chọn cần thiết. Nếu ứng dụng có nhiều tiến trình JVM, mỗi tiến trình cần cấu hình phù hợp.

### 6.2. Mô-đun đích phải có khả năng đọc mô-đun nguồn

Export và readability là hai điều kiện riêng. Thông thường mô-đun đích đã khai báo **requires** tới mô-đun nguồn. Nếu mô-đun đích chưa đọc mô-đun nguồn, cần xem lại quan hệ readability; **--add-exports** và **--add-opens** không thay thế một phụ thuộc đọc mô-đun bị thiếu.

### 6.3. Không mở rộng phạm vi hơn mức cần thiết

Ưu tiên một mô-đun đích cụ thể:

~~~bash
--add-opens com.example.lib/com.example.model=com.example.orm
~~~

Chỉ dùng **ALL-UNNAMED** khi thành phần cần quyền nằm trong unnamed module, thường là thư viện chạy từ classpath:

~~~bash
--add-opens com.example.lib/com.example.model=ALL-UNNAMED
~~~

Nếu dùng **ALL-UNNAMED**, mọi unnamed module có thể nhận quyền truy cập package đó. Phạm vi này rộng hơn một mô-đun đích cụ thể, vì vậy chỉ chọn khi kiến trúc classpath thực sự yêu cầu.

Không dùng cách mở toàn bộ mô-đun hoặc cấp quyền cho mọi bên nếu chỉ một package và một framework cần truy cập. Mỗi package mở thêm làm giảm mức đóng gói mà JPMS đang cung cấp.

### 6.4. Không nhầm với --add-reads

**--add-reads** bổ sung quan hệ readability giữa các mô-đun. **--add-exports** và **--add-opens** điều chỉnh quyền truy cập package. Nếu thông báo lỗi nói mô-đun không đọc mô-đun khác, hãy kiểm tra readability; nếu lỗi nói package chưa được export hoặc chưa mở cho reflection, hãy kiểm tra đúng tùy chọn export/open.

### 6.5. Không dựa vào cơ chế nới lỏng cũ

Không dựa vào tùy chọn **--illegal-access** để mở các package nội bộ. Các JDK hiện đại áp dụng strong encapsulation; giải pháp tích hợp cần dùng quyền export/open có mục tiêu hoặc cập nhật thư viện để dùng API được hỗ trợ.

## 7. Cấu hình khi triển khai

Các tùy chọn phải được truyền tới đúng JVM chạy ứng dụng hoặc framework. Đặt chúng ở tham số JVM của script khởi chạy, cấu hình service/container hoặc cấu hình test runner tương ứng.

Ví dụ một tiến trình chạy ứng dụng dạng module:

~~~bash
java --module-path lib ^
  --add-exports com.example.lib/com.example.internal=com.example.app ^
  --add-opens com.example.lib/com.example.model=com.example.orm ^
  -m com.example.app/com.example.app.Main
~~~

Khi dùng build tool, cần phân biệt JVM chạy build tool với JVM fork để chạy ứng dụng hoặc test. Tùy chọn đặt cho tiến trình build không nhất thiết tự động truyền sang tiến trình fork. Hãy kiểm tra command line thực tế của tiến trình cần truy cập package.

Sau khi tích hợp, ghi lại lý do, package nguồn, mô-đun đích và thành phần phụ thuộc cần quyền. Khi nâng cấp framework hoặc thư viện, thử bỏ từng tùy chọn để xem quyền đó còn cần thiết hay không.

## 8. Checklist trước khi thêm --add-exports hoặc --add-opens

- Xác định chính xác mô-đun sở hữu package và tên package cần truy cập.
- Xác định mô-đun đích; dùng tên mô-đun cụ thể nếu có thể.
- Xác định lỗi là truy cập kiểu public hay deep reflection.
- Dùng **--add-exports** khi cần truy cập thông thường vào package chưa export.
- Dùng **--add-opens** khi framework cần reflection vào thành viên không public.
- Thêm **--add-exports** ở bước biên dịch nếu mã nguồn cần import package đó, và thêm ở runtime nếu ứng dụng thực thi quyền truy cập.
- Chỉ thêm **--add-opens** vào runtime.
- Kiểm tra readability riêng nếu mô-đun đích chưa đọc mô-đun nguồn.
- Ưu tiên package và mô-đun đích cụ thể; chỉ dùng **ALL-UNNAMED** cho mã thuộc unnamed module.
- Tránh mở package không liên quan hoặc toàn bộ mô-đun khi không cần.
- Kiểm tra lại sau mỗi lần nâng cấp thư viện hoặc framework.

**Nguyên tắc áp dụng:** dùng **--add-exports** cho truy cập API thông thường và **--add-opens** cho deep reflection. Cấp quyền ở phạm vi nhỏ nhất, truyền vào đúng JVM và xem đây là cấu hình tích hợp có chủ đích. Nếu kiểm soát được thư viện, hãy cân nhắc sửa module descriptor hoặc thiết kế lại API để không cần dựa lâu dài vào các tùy chọn mở quyền từ dòng lệnh.