# Phân biệt quyền truy cập lúc biên dịch với cấu hình phản chiếu lúc chạy trong Java Modules

Trong Java Platform Module System (**JPMS**, có từ Java 9), một lớp được khai báo **public** chưa chắc đã truy cập được từ module khác. Khi chương trình sử dụng thư viện, cần phân biệt hai nhu cầu:

- **Truy cập tĩnh lúc biên dịch:** mã nguồn muốn **import, gọi constructor, method hay truy cập field** qua các quy tắc truy cập Java thông thường. JPMS dùng quan hệ đọc module (**readability**) và package được **exports**, cùng các access modifier như public/protected/private, để quyết định.
- **Truy cập bằng reflection lúc chạy:** framework muốn **tìm class, đọc annotation, tạo object hoặc đọc/ghi field bằng java.lang.reflect**. Nếu chỉ gọi public member được phép truy cập thông thường thì exports có thể đủ. Nếu cần **deep reflection** để bỏ kiểm tra access của private/package-private member, module sở hữu package thường phải **opens** package đó cho module thực hiện reflection.

Hai loại cấu hình này phục vụ những quyền khác nhau. **requires + exports** không tự cho phép đọc private field; **opens** không biến một package thành API có thể import lúc biên dịch.

## 1. Bối cảnh: package và module có hai tầng ranh giới

Một package tập hợp các type liên quan và chịu các quy tắc truy cập của ngôn ngữ (public, protected, package-private, private). Một **named module** tập hợp nhiều package và mô tả phụ thuộc cùng những package mà code bên ngoài được phép sử dụng.

Ví dụ:

~~~text
module demo.model
├── demo.model.api
│   └── Greeting.java       (API được công bố)
└── demo.model.internal
    └── Secret.java         (mã nội bộ)

module demo.consumer
└── demo.consumer
    └── Main.java
~~~

Ngay cả khi cả Greeting và Secret đều là **public class**, module demo.model có thể chỉ công bố package demo.model.api. Khi ấy code trong demo.consumer có thể dùng Greeting trực tiếp nếu có quan hệ đọc phù hợp, nhưng không thể import Secret từ package không được exports. Đây là **strong encapsulation ở mức module**.

**Vì sao cần thêm mức module?** Trước JPMS, một public class trên classpath thường có thể được import từ package khác. Từ khi đưa JAR thành explicit named module trên module path, module descriptor có thể ẩn toàn bộ package implementation dù chúng chứa public class. Một API công khai thực sự cần được công bố có chủ đích.

## 2. Các khái niệm không được nhầm lẫn

| Khái niệm | Quy tắc | Tác động chủ yếu |
| --- | --- | --- |
| **public class / public method** | Access modifier của Java | Kiểm tra truy cập tại cấp kiểu/thành viên; chưa bỏ qua ranh giới module |
| **requires module.name** | Module hiện tại khai báo phụ thuộc và đọc module đích | Điều kiện để code sử dụng API từ named module khác |
| **exports some.pkg** | Công bố package cho mọi module đọc module sở hữu | Cho phép truy cập public API lúc biên dịch và chạy |
| **exports some.pkg to friend.module** | Chỉ công bố cho module được liệt kê | API giới hạn người dùng |
| **opens some.pkg** | Mở package cho reflection lúc chạy | Cho phép deep reflection vào member không public từ module khác |
| **opens some.pkg to framework.module** | Chỉ mở cho module đã chỉ định | Giới hạn phạm vi deep reflection |
| **open module demo.model** | Mở toàn bộ package của module để reflection | Nới quyền reflection trên cả module |
| **--add-exports** | Tùy chọn của công cụ, thêm export ở phạm vi chạy/biên dịch phù hợp | Workaround cho truy cập API không được export |
| **--add-opens** | Tùy chọn của launcher, mở package khi chạy | Workaround cho deep reflection |
| **setAccessible(true)** | Yêu cầu bỏ qua kiểm tra Java access trong reflection | Chỉ thành công khi điều kiện quyền truy cập JPMS cho phép |

Theo Java Language Specification, **exports** giúp các module khác truy cập các type và thành viên public/protected khi đủ quan hệ đọc và quyền Java thông thường. **opens** cho phép reflection tại runtime, bao gồm cả những type/member không public; nó **không cấp quyền compile-time import** cho package chưa được exports.

Với một phần của API public đã được exports, reflection thông thường có thể gọi public method/constructor mà không cần opens. Chỉ khi cần điều chỉnh kiểm tra truy cập, ví dụ để chạm vào private field, vấn đề deep reflection mới trở nên nổi bật.

## 3. Readability: requires giải quyết quan hệ giữa module

Giả sử module ứng dụng cần dùng module thư viện:

~~~java
module demo.consumer {
    requires demo.model;
}
~~~

Khai báo này nói demo.consumer **đọc** demo.model. Nó không tự xuất mọi package của demo.model. Nếu module thư viện khai báo:

~~~java
module demo.model {
    exports demo.model.api;
}
~~~

thì demo.consumer có thể import public type từ **demo.model.api**. Nhưng **demo.model.internal** vẫn được đóng vì không có exports.

Hai điều kiện phải phối hợp:

1. Module tiêu thụ phải đọc module cung cấp (**requires**, hoặc một quan hệ đọc hợp lệ khác).
2. Package chứa type phải được exports cho module tiêu thụ; type và member còn phải đáp ứng quy tắc truy cập Java.

Lấy ví dụ: demo.consumer có requires nhưng demo.model không exports demo.model.api thì import public Greeting vẫn lỗi. Ngược lại, demo.model đã exports nhưng demo.consumer thiếu requires thì compiler cũng không tự suy ra quan hệ đọc từ một dòng import.

**Không đánh đồng requires với classpath.** Hai named module trong ví dụ thường được biên dịch/chạy trên **module path**, còn chương trình classpath thuộc **unnamed module** có quy tắc quan sát/đọc khác. Khi phân tích lỗi JPMS, xác định rõ mã chạy trên classpath, module path hay kết hợp cả hai.

## 4. exports: quyền sử dụng public API tại compile time

Trong module-info.java của thư viện:

~~~java
module demo.model {
    exports demo.model.api;
}
~~~

Chỉ package **demo.model.api** được xuất. Với module client có requires đúng, câu sau hợp lệ nếu Greeting là public:

~~~java
import demo.model.api.Greeting;
~~~

Tuy nhiên, chỉ public **class** là chưa đủ nếu một method được khai báo private. Ví dụ:

~~~java
package demo.model.api;

public class Greeting {
    public static String hello() {
        return "Xin chào";
    }

    private static String internalToken() {
        return "hidden";
    }
}
~~~

Client có thể gọi Greeting.hello(), nhưng không thể gọi Greeting.internalToken() như một method Java thông thường. **exports không làm private trở thành public.**

Nếu module chỉ muốn công bố API cho một module bạn bè:

~~~java
module demo.model {
    exports demo.model.api to demo.consumer;
}
~~~

Đây là **qualified export**. Những module khác không được liệt kê không có quyền truy cập API qua quan hệ module thông thường. Dù là qualified export, các access modifier trong package vẫn có hiệu lực.

### 4.1. exports và reflection thường

Ví dụ, client có một public class trong exported package với public method. Những reflective access thông thường như tìm public method bằng getMethod rồi gọi invoke thường được phép (với object và quyền truy cập tương ứng); không cần opens chỉ vì API của client sử dụng reflection.

Điểm khác biệt chỉ xuất hiện khi client muốn truy cập những member bị hạn chế và dùng **setAccessible(true)** hoặc **trySetAccessible()**. Một exported package **không tự cho phép** module khác bỏ qua private/protected/package-private access.

### 4.2. Qualified export không phải opens

Khai báo:

~~~java
exports demo.model.api to demo.consumer;
~~~

cấp quyền API cho demo.consumer, nhưng không có nghĩa demo.consumer được deep reflection vào private field trong package ấy. Nếu thực sự cần, descriptor có thể khai báo đồng thời:

~~~java
exports demo.model.api to demo.consumer;
opens demo.model.api to demo.consumer;
~~~

Hai dòng có hiệu ứng khác nhau. Chỉ thêm opens khi có use case reflection rõ ràng; nếu framework chỉ cần public API, không cần tự mở private member.

## 5. opens: quyền reflection tại runtime

Một số framework (dependency injection, ORM, JSON/XML binding, serializer, test tool) có thể cần tạo object bằng non-public constructor, đọc annotation trên private field hoặc gán giá trị field bằng reflection.

Một descriptor có thể cấp quyền như sau:

~~~java
module demo.model {
    exports demo.model.api;
    opens demo.model.internal to demo.consumer;
}
~~~

Ý nghĩa:

- **demo.model.api** vẫn là API công bố để Java code bên module khác sử dụng tĩnh.
- **demo.model.internal** không được exports, nên demo.consumer **không thể import trực tiếp class ở đó** chỉ nhờ opens.
- demo.consumer được phép yêu cầu quyền reflective access vào các type/member của demo.model.internal tại runtime, kể cả private nếu sử dụng API reflection phù hợp.
- Các module không có tên trong **to demo.consumer** không nhận quyền deep reflection từ khai báo này.

Nếu bỏ **to demo.consumer**:

~~~java
opens demo.model.internal;
~~~

package được mở cho reflection của mọi module, phạm vi rộng hơn. Khi đã biết module framework thực sự cần quyền, **qualified opens** thường rõ và hẹp hơn.

**Điểm quan trọng:** opens không tự chạy reflection. Mã Java phải thực sự gọi API như Class.forName, getDeclaredField, getDeclaredConstructor, setAccessible hoặc công cụ framework tương đương. Opens chỉ gỡ rào cản tại module boundary đối với những thao tác được cho phép.

### 5.1. setAccessible và trySetAccessible có gì khác?

Khi gọi:

~~~java
field.setAccessible(true);
~~~

Java kiểm tra liệu caller có thể tắt access check cho field đó hay không. Nếu package nằm trong named module khác và chưa được mở phù hợp, thao tác có thể ném **java.lang.reflect.InaccessibleObjectException**.

Dạng không ném ngoại lệ khi chỉ không đủ quyền tương ứng:

~~~java
boolean allowed = field.trySetAccessible();
~~~

Nếu không được phép bật access, trySetAccessible thường trả về **false**, giúp code chủ động xử lý tình huống framework thiếu opens. Đây vẫn là một thao tác có kiểm tra quyền, không phải cách vượt qua encapsulation. Các bất thường khác vẫn có thể xảy ra tùy đối tượng reflection và security context.

Với **public member của public class thuộc exported package**, reflective access thông thường có thể thành công mà không cần gọi setAccessible. Với **private member xuyên module**, thường phải có opens và yêu cầu suppress access hợp lệ.

### 5.2. Mở package không đồng nghĩa đối tượng tự xuất hiện

Class.forName có thể nạp một class có tên đầy đủ khi class loader/module resolution tìm thấy class ấy. Nhưng **tìm/nạp được Class object** và **có quyền tạo instance hoặc đọc field** là hai câu hỏi riêng. Một class thuộc unexported package có thể tìm bằng reflection, rồi thất bại khi code cố truy cập constructor do Java access/module checks.

Ví dụ minh họa trong phần 7 sử dụng đặc điểm này để làm rõ lỗi.

## 6. Ma trận quyền: truy cập tĩnh và reflection

Giả sử client ở module khác có quan hệ đọc phù hợp, type được khai báo **public**, và người dùng không có thêm override qua dòng lệnh:

| Descriptor của package | Import/gọi public type lúc compile? | Gọi public member qua reflection thông thường? | Deep reflection vào private field? |
| --- | --- | --- | --- |
| Không exports, không opens | Không | Không được phép truy cập thành viên theo thông lệ | Không |
| **exports pkg;** | Có | Có (nếu điều kiện Java access phù hợp) | Không |
| **opens pkg;** | Không | Có thể truy cập phản chiếu tại runtime | Có, nếu dùng API reflection đúng |
| **exports pkg; opens pkg;** | Có | Có | Có |
| **exports pkg to M;** | Có đối với M | Có đối với M | Không chỉ từ exports |
| **opens pkg to M;** | Không chỉ từ opens | Có với M | Có với M |
| **open module ...** (không exports pkg) | Không | Có khả năng reflection ở runtime | Có |

Bảng là mô hình phổ biến khi module/package được resolve đúng. Một quyền reflective access còn phụ thuộc module **thực hiện** reflection, loại thành viên, access modifier, class loader, và API được sử dụng. Nó không có nghĩa mọi lời gọi reflection đều thành công bất kể tên constructor/method hoặc giá trị đối số.

**Một public type có thể bị đóng ở mức package.** Và một private field có thể vẫn đóng trước reflection dù package đã được exports. Đó là hai tầng truy cập tách biệt.

## 7. Ví dụ Java 17+: hai module, public API và private field

Ví dụ này có hai module thực sự, chạy được với JDK 17+. Module **demo.model** xuất một package public API và giữ một package internal để thử reflection. Module **demo.consumer** dùng API tĩnh, sau đó cố đọc private field bằng reflection.

### 7.1. Cấu trúc dự án

Tạo các tệp:

~~~text
src/
├── demo.model/
│   ├── module-info.java
│   └── demo/
│       └── model/
│           ├── api/
│           │   └── Greeting.java
│           └── internal/
│               └── Secret.java
└── demo.consumer/
    ├── module-info.java
    └── demo/
        └── consumer/
            └── Main.java
~~~

**Tệp src/demo.model/module-info.java:**

~~~java
module demo.model {
    exports demo.model.api;
}
~~~

Chưa có opens. Đây là trạng thái đầu tiên để quan sát reflection bị chặn.

**Tệp src/demo.model/demo/model/api/Greeting.java:**

~~~java
package demo.model.api;

public final class Greeting {
    private Greeting() {}

    public static String message() {
        return "Public API OK";
    }
}
~~~

**Tệp src/demo.model/demo/model/internal/Secret.java:**

~~~java
package demo.model.internal;

public final class Secret {
    private final String code = "vault-42";

    public Secret() {}
}
~~~

Secret được khai báo public để dễ minh họa sự khác nhau giữa **public type** và **exported package**. Package demo.model.internal vẫn không được exports, nên client không thể import Secret trực tiếp. Field code là private, nên ngay cả exports package cũng không tự cho code bên ngoài đọc trực tiếp field.

**Tệp src/demo.consumer/module-info.java:**

~~~java
module demo.consumer {
    requires demo.model;
}
~~~

**Tệp src/demo.consumer/demo/consumer/Main.java:**

~~~java
package demo.consumer;

import demo.model.api.Greeting;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(Greeting.message());

        Class<?> secretType =
                Class.forName("demo.model.internal.Secret");

        Constructor<?> constructor =
                secretType.getDeclaredConstructor();

        try {
            constructor.setAccessible(true);
            Object secret = constructor.newInstance();

            Field field = secretType.getDeclaredField("code");
            field.setAccessible(true);

            System.out.println("Secret: " + field.get(secret));
        } catch (InaccessibleObjectException exception) {
            System.out.println("Deep reflection BLOCKED");
        }
    }
}
~~~

**Giải thích lộ trình:**

1. Dòng import **demo.model.api.Greeting** và lệnh gọi Greeting.message() sử dụng **readability + exports**.
2. Client lấy **Class<?>** bằng tên đầy đủ của Secret, không cần import Secret.
3. **getDeclaredConstructor()** lấy mô tả constructor, chưa tự cấp quyền truy cập.
4. **constructor.setAccessible(true)** yêu cầu quyền deep reflection vào class của package chưa được opened.
5. Nếu module vẫn đóng package, JPMS từ chối thao tác setAccessible bằng InaccessibleObjectException và chương trình in dòng thông báo chủ động.
6. Nếu package được mở cho demo.consumer, việc bật access và đọc private field có thể thành công.

### 7.2. Biên dịch và chạy khi chưa opens

Từ thư mục chứa **src**, dùng lệnh:

~~~bash
javac -d out --module-source-path src -m demo.model,demo.consumer
java --module-path out -m demo.consumer/demo.consumer.Main
~~~

**Standard output mong đợi trên JDK 17+:**

~~~text
Public API OK
Deep reflection BLOCKED
~~~

Khi source có mã như trên, compiler vẫn thành công: client không import/internal type; thông tin package internal chỉ được tìm bằng tên tại runtime. Việc thiếu opens được phát hiện ở **lời gọi setAccessible(true) lúc chạy**.

Nếu bỏ try/catch, InaccessibleObjectException sẽ lan ra và kèm stack trace chứa lý do module demo.model không opens package demo.model.internal tới demo.consumer. Đây **không phải lỗi thiếu requires** và cũng không có nghĩa Java không tìm được class file.

### 7.3. Mở đúng package cho đúng module

Sửa duy nhất descriptor của **demo.model** thành:

~~~java
module demo.model {
    exports demo.model.api;
    opens demo.model.internal to demo.consumer;
}
~~~

Biên dịch lại và chạy lại:

~~~bash
javac -d out --module-source-path src -m demo.model,demo.consumer
java --module-path out -m demo.consumer/demo.consumer.Main
~~~

**Standard output mong đợi:**

~~~text
Public API OK
Secret: vault-42
~~~

Khai báo **opens demo.model.internal to demo.consumer** cho phép module demo.consumer thực hiện deep reflection tại runtime. Phương thức và field vẫn private theo luật Java thông thường; **không thể viết secret.code** trực tiếp trong code client.

**Lưu ý về đoạn mã:** Đây là chương trình hoàn chỉnh và có thể tự tạo đúng các tệp để chạy; hai phiên bản module-info.java là **hai lần thử thay thế nhau**, không được đặt cả hai module descriptor cùng lúc. Thay descriptor rồi biên dịch lại để quan sát hiệu ứng.

### 7.4. Dùng tham số dòng lệnh thay cho sửa descriptor

Nếu muốn giữ module-info.java của demo.model ở trạng thái **chỉ exports API**, có thể cấp quyền mở tại lần khởi chạy để chẩn đoán hoặc hỗ trợ thư viện cũ:

~~~bash
java --add-opens demo.model/demo.model.internal=demo.consumer --module-path out -m demo.consumer/demo.consumer.Main
~~~

Lệnh này mở package **demo.model.internal** của module **demo.model** cho module **demo.consumer** tại runtime. Khi chạy từ artifact đã biên dịch trước đó mà chưa có opens, đầu ra trở thành:

~~~text
Public API OK
Secret: vault-42
~~~

Tùy chọn **--add-opens** không tự sửa source descriptor và không làm package trở thành exported ở **compile time**. Vì thế vẫn không thể biên dịch một lời gọi trực tiếp tới Secret trong client chỉ bằng lệnh chạy trên.

**Thực hành an toàn:** Ưu tiên mô tả quyền phản chiếu cần thiết bằng opens có phạm vi rõ ràng nếu sở hữu mã nguồn module. Chỉ dùng **--add-opens** khi cần điều khiển ở deployment/migration hoặc không thể sửa descriptor của thư viện.

## 8. Chứng minh opens không thay thế exports

Giả sử module demo.model giữ:

~~~java
module demo.model {
    exports demo.model.api;
    opens demo.model.internal to demo.consumer;
}
~~~

Client thử thêm import trực tiếp:

~~~java
// Minh họa một import không hợp lệ ở demo.consumer:
import demo.model.internal.Secret;
~~~

Đoạn này **không phải source file hoàn chỉnh**; nó minh họa import sẽ bị javac từ chối vì demo.model.internal **chưa được exports**. Compiler có thể báo package được khai báo trong module demo.model nhưng không visible/exported tới module demo.consumer.

Muốn compiler cho phép code client sử dụng **public Secret** trực tiếp thì cần **exports demo.model.internal** (hoặc qualified export cho demo.consumer), bên cạnh requires phù hợp. Nhưng đây thường không phải thiết kế mong muốn: internal Secret không nhất thiết là API ổn định, framework chỉ cần reflection.

Ngay cả nếu sửa descriptor thành:

~~~java
module demo.model {
    exports demo.model.api;
    exports demo.model.internal;
}
~~~

thì access vào **private field code** bằng setAccessible từ module khác **vẫn bị chặn** nếu package không được opens. Chỉ thay **exports** không giải quyết use case deep reflection.

Từ đó:

- **Lỗi import không nhìn thấy package:** xem requires và exports.
- **Lỗi setAccessible bị từ chối:** xem opens, module caller và loại access được yêu cầu.
- **Lỗi tên class không tồn tại:** xem module resolution, module path, class loader, package và tên class.
- **Lỗi member không tồn tại:** xem chữ ký method/constructor/field; mở package không tự sinh member thiếu.

## 9. open module so với opens một package

Nếu một module có nhiều package cần reflection, Java hỗ trợ cú pháp:

~~~java
open module demo.model {
    exports demo.model.api;
}
~~~

Đây là **open module**: mọi package trong module được mở cho deep reflection ở runtime, dù không được exports. Tuy vậy, compile-time direct access từ module khác vẫn chỉ được phép đối với những package đã exports đúng cách.

**Không xem open module như tương đương với exports toàn bộ package.** Nó thay đổi quyền reflection, không công bố mọi implementation type thành API compile-time.

Khi mô-đun dùng nhiều framework cần access non-public members, open module có thể thuận tiện cho thử nghiệm hoặc môi trường migration. Nhưng nó mở quá rộng nếu chỉ một package thực sự cần phản chiếu. Trong thiết kế thư viện, thường chọn:

~~~java
module demo.model {
    exports demo.model.api;
    opens demo.model.entity to example.orm;
}
~~~

Đây là **mã minh họa**: example.orm phải thay bằng tên module thực của framework trong hệ thống. Không sao chép một module name không tồn tại vào ứng dụng và kỳ vọng nó tự tải dependency.

**Kỹ thuật:** Trong khai báo **open module**, không kết hợp thêm những chỉ thị opens riêng lẻ như trong normal module; open module đã mở toàn bộ package. Nếu cần kiểm soát theo package hoặc theo module caller, dùng normal module cùng các qualified opens.

## 10. Qualified opens và phạm vi quyền

Có hai dạng:

~~~java
opens demo.model.internal;
~~~

và:

~~~java
opens demo.model.internal to demo.consumer;
~~~

Dạng thứ nhất mở cho **mọi module**. Dạng thứ hai chỉ mở cho **demo.consumer**. Điều này quan trọng khi có nhiều framework cùng chạy:

- Nếu một module mapper cần đọc field của các entity, nên mở đúng package entity cho **module tên thật của mapper**.
- Nếu một thư viện serialization khác cần reflection riêng, phải mở thêm cho module thư viện đó hoặc cấu hình giải pháp tương ứng.
- Một chương trình chạy từ classpath thường nằm trong **unnamed module**. Khi dùng tùy chọn dòng lệnh, đích **ALL-UNNAMED** giúp mở cho mọi unnamed module, ví dụ cú pháp minh họa:

~~~bash
java --add-opens demo.model/demo.model.internal=ALL-UNNAMED -cp app.jar app.Main
~~~

Đây chỉ là **minh họa cú pháp**. Muốn lệnh chạy thực tế còn phải bảo đảm module demo.model được tìm/resolved trong cấu hình khởi chạy; riêng **-cp app.jar** không đủ chứng minh demo.model đã được resolve. Dùng named module cụ thể trong cấu hình nếu có thể, vì ALL-UNNAMED mở quyền rộng hơn.

**Qualified opens không có nghĩa module caller phải tự ghi requires để reflection hoạt động trong mọi hoàn cảnh**, nhưng module chứa class vẫn phải được resolve và có thể nhìn thấy bởi class loader. Trong chương trình modular thông thường, dependency requires là cách dễ hiểu để đảm bảo module cần thiết được resolve. Khi dùng reflection động và module không có quan hệ đọc tường minh, phải kiểm tra module resolution/loader thực tế thay vì suy ra từ import.

## 11. --add-exports và --add-opens khác nhau ra sao?

Công cụ JDK cung cấp các tùy chọn để điều chỉnh package boundary khi chưa thể sửa module descriptor. Hai tùy chọn không tương đương.

| Option | Mục đích | Thời điểm cần quan tâm |
| --- | --- | --- |
| **--add-exports source.module/pkg=target.module** | Cho target module truy cập public type/member trong package chưa exports theo cấu hình bình thường | Compile và/hoặc runtime khi dùng API internal theo cách Java thông thường |
| **--add-opens source.module/pkg=target.module** | Cho target module deep reflection vào package | Runtime, khi reflection cần bỏ Java access check |
| **--add-reads source.module=target.module** | Thêm quan hệ đọc module trong những trường hợp module graph cần điều chỉnh | Compile hoặc runtime tùy công cụ và tình huống |

Ví dụ:

~~~bash
java --add-exports demo.model/demo.model.internal=demo.consumer --module-path out -m demo.consumer/demo.consumer.Main
~~~

Tùy chọn **--add-exports** ở runtime chỉ bổ sung export cho public API của package cho target; nó **không** tự cho phép caller bật accessible cho private field của Secret. Nếu chương trình Main vẫn cần private field, phải mở package bằng **--add-opens**, không chỉ add-exports.

Khi biên dịch source trực tiếp sử dụng internal API, các tùy chọn add-exports có thể phải được cấu hình **ở cả javac và java** tương ứng. Chỉ thêm override khi chạy không làm cho một lỗi import trước đó trở thành source biên dịch được.

**Lưu ý:** các lựa chọn này tạo ngoại lệ cho strong encapsulation và làm tăng sự phụ thuộc vào implementation không được công bố là public API ổn định. Chúng phù hợp cho chuyển đổi hoặc chẩn đoán có chủ đích, cần được ghi lại trong build/deployment. Không nên giải quyết mọi lỗi quyền truy cập bằng cách mở toàn bộ package của JDK.

## 12. Reflection API: quyền thực tế phụ thuộc cách truy cập

Một số API quen thuộc:

| API hoặc hành động | Cần lưu ý |
| --- | --- |
| **Class.forName(name)** | Nạp/resolve class theo class loader phù hợp; không tự cấp quyền truy cập constructor/field |
| **getMethod(...)** | Tìm public method thỏa tên/chữ ký; gọi method còn qua kiểm tra truy cập |
| **getDeclaredMethod(...)** | Tìm method được khai báo trực tiếp kể cả private; lấy Method object chưa cho phép invoke nếu thiếu quyền |
| **getConstructor(...)** | Tìm public constructor; không tự bỏ module access checks |
| **getDeclaredConstructor(...)** | Lấy constructor khai báo trực tiếp kể cả non-public |
| **getField(...) / getDeclaredField(...)** | Lấy public/inherited field hoặc field khai báo trực tiếp |
| **setAccessible(true)** | Yêu cầu bỏ Java language access checks; cần điều kiện JPMS cho phép |
| **trySetAccessible()** | Thử bật accessible; có thể trả false nếu quyền không đủ |
| **Method.invoke / Constructor.newInstance / Field.get** | Thực thi/truy cập, còn phụ thuộc quyền, đối tượng và chữ ký |

**Một số nhầm lẫn thường gặp:**

- Lấy được **Field** bằng getDeclaredField không chứng tỏ đọc được private field.
- **Public class** trong package không được exports vẫn không trở thành API compile-time của module khác.
- Reflection vào **public method của exported public type** có thể thực hiện mà không opens; không phải mọi reflection đều là deep reflection.
- Đọc được annotation metadata công khai cũng không đồng nghĩa có quyền sửa field private.
- Mở package không bảo đảm API reflection không thất bại vì đối tượng null, sai constructor arguments, invocation exception hoặc giá trị không tương thích.

### 12.1. InaccessibleObjectException và IllegalAccessException

Khi code **cố bật setAccessible(true)** để vượt rào module chưa opened, Java thường ném **InaccessibleObjectException** ngay ở thao tác bật access.

Khi code **không bật accessible**, nhưng gọi constructor/method/field vốn không truy cập được bằng các quy tắc bình thường, API reflection có thể báo **IllegalAccessException**.

Chúng cùng liên quan quyền, nhưng vị trí và nguyên nhân khác nhau. Không nên catch một exception rồi mặc định mọi lỗi còn lại đều do opens.

### 12.2. Vì sao Java 17+ dễ lộ lỗi này hơn?

Trong một số giai đoạn chuyển tiếp của JDK 9–16, JVM từng cho phép một số illegal reflective access để hỗ trợ ứng dụng cũ cùng cảnh báo. Từ **JDK 17**, strong encapsulation áp dụng mặc định nghiêm hơn đối với nhiều internals của JDK (JEP 403). Vì vậy một framework cũ dùng setAccessible vào internals của java.base có thể gặp InaccessibleObjectException khi nâng JDK.

Giải pháp ưu tiên là cập nhật framework/thư viện hoặc chuyển sang API được hỗ trợ. Nếu không thể chuyển ngay, dùng **--add-opens** hạn chế phạm vi và document lý do. Tùy chọn legacy **--illegal-access** không còn là cách bật lại quyền reflective access rộng như trước trên JDK 17+.

## 13. Khi cấu hình framework trong dự án thực tế

Giả sử có **domain.entity.Customer** với các private field, và một framework ORM/serializer cần tạo hoặc gán state bằng reflection.

Có thể dùng một module descriptor minh họa:

~~~java
module example.application {
    requires example.orm;
    exports example.application.api;

    opens example.application.entity to example.orm;
}
~~~

Đây là **cú pháp minh họa**: example.orm và các package cần thay bằng tên đúng của module/framework thực sự. Không có giả định mọi ORM hoạt động như nhau; một số framework dùng public constructor, bytecode enhancement, MethodHandles, annotation processing hoặc code generation và có yêu cầu cấu hình khác.

Để quyết định giữa exports và opens:

1. **Framework hoặc module khác có cần import/call API public của package này không?** Nếu có, cân nhắc exports cho đúng client.
2. **Framework có dùng reflection để chạm vào non-public member ở runtime không?** Nếu có, cân nhắc opens package cho module framework.
3. **Có thể thiết kế public API hoặc adapter để tránh deep reflection không?** Nếu có, đó có thể là lựa chọn ít quyền hơn.
4. **Module framework có tên ổn định không?** Xác minh tên module khi dùng qualified opens. Với thư viện chạy classpath/unnamed module, cách cấu hình có thể khác.
5. **Có phải cả package đều cần mở không?** JPMS opens được khai báo theo package, không theo một field riêng. Thiết kế package nên tránh trộn dữ liệu nhạy cảm với các type framework phải reflect.
6. **Có cần sự tương thích giữa bản JVM/IDE/test runner và runtime production?** Kiểm tra trên đúng module path, không dựa vào việc test đang chạy từ classpath.

Không nên tự thêm **open module** chỉ vì một package model cần mapping. Qualified opens hoặc public API riêng thường giúp giữ ranh giới rõ ràng.

## 14. Cách chẩn đoán lỗi theo từng giai đoạn

| Triệu chứng | Thời điểm | Điều cần kiểm tra trước |
| --- | --- | --- |
| **package ... is not visible** | Compile | requires, exports (và qualified export target), module path |
| **module not found** | Compile hoặc module resolution lúc chạy | Module path, tên module, descriptor, dependency |
| **cannot find symbol** | Compile | Import/tên type, compile classpath/module path, member signature |
| **IllegalAccessError** | Runtime linkage | Có thể do thay đổi exports/module visibility hoặc binary incompatibility |
| **ClassNotFoundException** | Runtime | Tên class, class loader, module đã resolve hay chưa |
| **IllegalAccessException** | Runtime reflection | Quyền truy cập thông thường khi gọi constructor/method/field |
| **InaccessibleObjectException** | Runtime reflection | setAccessible bị từ chối: kiểm tra opens và module caller |
| **NoSuchFieldException/NoSuchMethodException** | Runtime reflection | Tên member, chữ ký, declared/public API; opens không tạo member |
| **InvocationTargetException** | Runtime reflection | Ngoại lệ do method/constructor thực sự ném ra; đọc cause |

Một tình huống điển hình:

~~~text
Lúc compile: import public API thành công
    |
    v
Lúc runtime: Class.forName tìm được implementation class
    |
    v
getDeclaredField tìm được private field
    |
    v
setAccessible(true) bị InaccessibleObjectException
    |
    v
Bổ sung opens đúng package đến đúng caller
~~~

Ngược lại, nếu compiler không cho import class ngay từ đầu, bổ sung opens đơn thuần không chữa lỗi compile-time. Khi lỗi đến từ thư viện không nằm trên module path hoặc module chưa resolve, phải sửa dependency/module resolution trước.

### 14.1. Xem module descriptor và module path

Các lệnh có ích:

~~~bash
java --module-path out --describe-module demo.model
~~~

Lệnh hiển thị những thông tin module descriptor được nạp như requires và exports/opens. Cách trình bày dòng output phụ thuộc JDK và descriptor đang dùng nên không gán stdout cố định.

~~~bash
java --show-module-resolution --module-path out -m demo.consumer/demo.consumer.Main
~~~

Lệnh giúp quan sát các module được resolve khi khởi chạy. Nếu runtime vẫn không tìm được module, cần xác minh cây out, tên module và cách đóng gói JAR.

Khi sử dụng JAR trên module path, có thể xem descriptor bằng lệnh **jar --describe-module --file path/to/library.jar** nếu JAR có metadata module phù hợp.

## 15. Quy tắc thực hành và lưu ý bảo mật

**exports là quyết định công bố API.** Mở rộng export có thể khiến các ứng dụng khác bắt đầu phụ thuộc vào implementation class; việc rút lại export sau này có thể phá vỡ tương thích. Nên chỉ exports package thật sự được thiết kế như API.

**opens là quyết định cấp quyền reflection.** Một thư viện được quyền đọc/ghi private field có thể vượt qua nhiều bất biến đóng gói ở mức class. Chỉ mở package cần thiết đến đúng module có nhu cầu. Dùng **ALL-UNNAMED** hoặc open module khi hiểu rõ phạm vi ảnh hưởng.

**Cả hai không thay thế quy trình kiểm thử.** Cấu hình runtime khác với compile có thể gây lỗi chỉ xuất hiện ở production. Với JDK 17+, kiểm thử cùng kiểu khởi chạy (classpath hoặc module path), cùng tên module và cùng launcher options.

**Giới hạn quyền là một phần thiết kế kiến trúc.** Package API phục vụ use case được bảo đảm ổn định; package internal chỉ dành cho implementation và có thể mở rất hẹp cho framework nếu bắt buộc.

**Đừng nhầm cấu hình thư viện với giấy phép vô điều kiện.** JPMS mở khả năng reflection theo package/module, nhưng mã vẫn chịu các điều kiện riêng của reflection API, class loader, tính hợp lệ của thao tác và các biện pháp bảo vệ hệ thống khác.

## 16. Bài tập vận dụng

### Bài 1: Chọn directives

Bạn có module **sales.model** với package **sales.model.api** chứa public DTO cho ứng dụng khác, và package **sales.model.entity** chứa private fields mà serializer trong module **json.mapper** cần truy cập.

Hãy viết module-info.java tương ứng: exports API; opens entity chỉ cho json.mapper; requires cần thiết theo dependency thật của module. Giải thích vì sao không cần exports entity nếu client không import class của package này.

### Bài 2: Thay đổi quyền theo từng lượt

Dùng ví dụ demo.model và demo.consumer ở phần 7:

1. Chạy khi chỉ có exports API.
2. Thêm **opens demo.model.internal to demo.consumer** và chạy lại.
3. Thử bỏ opens và chỉ **exports demo.model.internal**; quan sát việc đọc private field.
4. Thử giữ descriptor gốc và thêm **--add-opens** khi khởi chạy.

Ghi lại stdout và nguyên nhân của từng thay đổi.

### Bài 3: Phân biệt lỗi

Với một public class trong unexported package, client thử import class: lỗi ở compile hay runtime? Nếu thay import bằng Class.forName và gọi setAccessible trên constructor, lỗi có thể chuyển sang giai đoạn nào? Điều gì khác đi khi package được qualified opens?

### Bài 4: Phân biệt API reflection

Cho Class object của một class có private field, giải thích sự khác nhau giữa:

- **getField("secret")** và **getDeclaredField("secret")**.
- **field.get(instance)** và **field.setAccessible(true); field.get(instance)**.
- **field.trySetAccessible() == false** và một thao tác reflection thành công.

Một member không public có thể được tìm thấy trong metadata nhưng chưa chắc được phép sử dụng.

### Bài 5: Audit module descriptor

Trong một ứng dụng đã modular hóa, kiểm tra từng **exports**, **opens** và **--add-opens**. Với mỗi entry, xác định ai đang dùng quyền đó, use case là compile-time API hay runtime reflection, có thể thu hẹp phạm vi bằng **to module.name** không, và đã test trên phiên bản JDK chạy thực tế chưa.

## 17. Câu hỏi tự kiểm tra

- Vì sao public class trong named module vẫn có thể không import được từ module khác?
- **requires** giải quyết vấn đề gì, và **exports** giải quyết vấn đề gì?
- Một exported package có cho module khác đọc private field bằng reflection không?
- **opens** có làm import class trong unexported package được phép lúc compile không?
- Vì sao Class.forName thành công không đồng nghĩa Constructor.newInstance được phép?
- Sự khác nhau giữa **setAccessible(true)** và **trySetAccessible()** là gì?
- Khi nào sử dụng **qualified opens** thay vì open module?
- **--add-exports** có thay cho **--add-opens** khi cần private field không?
- Với chương trình nằm trên classpath, **ALL-UNNAMED** nghĩa là gì?
- Trong stack trace, dấu hiệu nào gợi ý thiếu opens thay vì thiếu dependency?
- Vì sao nên cập nhật framework thay vì mở rộng quyền vào internals của JDK vô thời hạn?

## 18. Tài liệu tham khảo chính thức

- **Java Language Specification 21, §7.7.2 – Exported and Opened Packages:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.2
- **Dev.java – Reflective Access with Open Modules and Open Packages:** https://dev.java/learn/organizing/modules/opening-for-reflection/
- **Dev.java – Qualified exports and opens:** https://dev.java/learn/organizing/modules/qualified-exports-opens/
- **Dev.java – Circumventing Strong Encapsulation with --add-exports and --add-opens:** https://dev.java/learn/organizing/modules/add-exports-opens/
- **Oracle Java SE 21, AccessibleObject API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- **Oracle Java 21, java launcher options:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- **OpenJDK JEP 403 – Strongly Encapsulate JDK Internals:** https://openjdk.org/jeps/403

**Ghi nhớ:** Với **mã Java gọi API công khai**, dùng quan hệ đọc module và **exports** đúng phạm vi. Với **framework cần deep reflection vào non-public members**, dùng **opens** đúng package và đúng module caller. **exports là công bố API cho truy cập thông thường; opens là cấp quyền truy cập phản chiếu tại runtime.**