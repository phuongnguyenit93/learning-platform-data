# Điều kiện một type được access từ module khác trong Java Module System

## 1. Mục tiêu bài học

Kể từ Java 9, Java Platform Module System (JPMS) bổ sung ranh giới truy cập ở cấp **module**. Một kiểu dữ liệu (`class`, `interface`, `enum`, `record` hoặc annotation type) có khai báo `public` chưa đủ để mã trong một **named module** khác có thể sử dụng trực tiếp kiểu đó.

Bài này tập trung vào câu hỏi: **Một type ở module A cần thỏa điều kiện gì để mã ở module B truy cập được?**

Sau khi học, bạn có thể:

- Giải thích ba tầng kiểm soát truy cập: **module readability**, **package exports** và **Java accessibility**.
- Tự dựng hai named module để quan sát cả trường hợp truy cập thành công lẫn bị trình biên dịch từ chối.
- Phân biệt `requires`, `requires transitive`, `exports`, `exports ... to`, `opens` và các tùy chọn bổ sung quyền.
- Xác định điều kiện truy cập của lớp lồng nhau, thành viên, kiểu trả về và kiểu tham số trong API.
- Chẩn đoán nguyên nhân lỗi khi một `public` type “tồn tại nhưng không thể import”.

## 2. Mô hình ba điều kiện truy cập

Giả sử module `consumer.app` muốn sử dụng type `org.example.library.api.Greeting` trong module `library.core`. Khi nói tới **truy cập thông thường từ mã Java** ở một named module khác, phải xét đồng thời:

**Điều kiện 1 — Module B đọc được module A (readability).**

`consumer.app` cần có quan hệ đọc tới `library.core`. Cách thông dụng là khai báo:

~~~java
module consumer.app {
    requires library.core;
}
~~~

Quan hệ đọc cũng có thể đến từ một số cơ chế JPMS khác, chẳng hạn `requires transitive` từ module trung gian hoặc cấu hình bổ sung `--add-reads`. Tự biết tên module A hoặc đặt JAR của A trên module path chưa mặc nhiên thay thế quan hệ đọc.

**Điều kiện 2 — Package chứa type được module A export cho B.**

Trong descriptor của `library.core` phải có một trong hai dạng phù hợp:

~~~java
module library.core {
    exports org.example.library.api;
}
~~~

Hoặc chỉ mở package cho module nhận quyền cụ thể:

~~~java
module library.core {
    exports org.example.library.api to consumer.app;
}
~~~

`exports` là khai báo ở **cấp package**, không cấp từng class. Export `org.example.library.api` không tự export `org.example.library.internal` hay các package con có tên bắt đầu giống nhau.

**Điều kiện 3 — Bản thân type accessible theo Java Language Specification.**

Nếu hai package ở hai module khác nhau, một top-level type muốn được gọi trực tiếp từ bên ngoài phải là `public`. Nếu đó là nested type, còn phải xét accessibility của lớp bao ngoài và của chính nested type. Đối với trường hợp gọi constructor, field hoặc method, phải kiểm tra thêm accessibility của **thành viên** tương ứng.

Ba điều kiện kết hợp:

~~~text
Mã tại consumer.app
         |
         | 1. consumer.app đọc được library.core?
         v
   Module library.core
         |
         | 2. Package của Greeting được exports tới consumer.app?
         v
 org.example.library.api
         |
         | 3. Greeting là public / accessible theo Java?
         v
   Sử dụng Greeting được
~~~

Có thể diễn đạt ngắn gọn:

> **Access qua biên giới named module = readability phù hợp + package được export cho module gọi + access modifier hợp lệ.**

Đây là mô hình cho **truy cập thông thường** tới kiểu trong các named modules. Truy cập qua reflection, module tự động và code chạy trên classpath có các chi tiết riêng, được đề cập bên dưới.

## 3. Ví dụ chạy được: hai named modules

Ta tạo module thư viện `library.core` và module sử dụng `consumer.app`.

### 3.1. Cấu trúc thư mục

~~~text
project/
├── src/
│   ├── library.core/
│   │   ├── module-info.java
│   │   └── org/example/library/
│   │       ├── api/Greeting.java
│   │       └── internal/TextFormatter.java
│   └── consumer.app/
│       ├── module-info.java
│       └── org/example/app/Main.java
└── out/                    # javac tạo ra sau khi biên dịch
~~~

### 3.2. Module cung cấp type

File `src/library.core/module-info.java`:

~~~java
module library.core {
    exports org.example.library.api;
}
~~~

File `src/library.core/org/example/library/api/Greeting.java`:

~~~java
package org.example.library.api;

import org.example.library.internal.TextFormatter;

public final class Greeting {
    private Greeting() {}

    public static String sayHello(String name) {
        return TextFormatter.format(name);
    }
}
~~~

File `src/library.core/org/example/library/internal/TextFormatter.java`:

~~~java
package org.example.library.internal;

public final class TextFormatter {
    private TextFormatter() {}

    public static String format(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`TextFormatter` là một top-level class `public`, nhưng package `internal` **không được export**. `Greeting` vẫn gọi được `TextFormatter` vì cả hai nằm trong cùng module `library.core` và access modifier cho phép.

### 3.3. Module tiêu thụ type

File `src/consumer.app/module-info.java`:

~~~java
module consumer.app {
    requires library.core;
}
~~~

File `src/consumer.app/org/example/app/Main.java`:

~~~java
package org.example.app;

import org.example.library.api.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.sayHello("Java"));
    }
}
~~~

Từ thư mục `project`, biên dịch các module:

~~~shell
javac --module-source-path src -d out -m library.core,consumer.app
~~~

Chạy module ứng dụng:

~~~shell
java --module-path out -m consumer.app/org.example.app.Main
~~~

Kết quả:

~~~text
Hello, Java!
~~~

Giải thích:

1. `consumer.app` có `requires library.core;` nên đọc được `library.core`.
2. `library.core` export package `org.example.library.api` không giới hạn.
3. `Greeting` và `sayHello` là `public`; tên type và thành viên phù hợp với luật truy cập Java.

Tất cả điều kiện cần đều thỏa mãn nên chương trình chạy được.

## 4. Thiếu một điều kiện thì điều gì xảy ra?

### 4.1. Module không đọc được module cung cấp

Bỏ dòng `requires library.core;` trong descriptor của `consumer.app`, nhưng vẫn giữ lệnh `import org.example.library.api.Greeting;`.

Trình biên dịch không cho phép consumer truy cập package qua module chưa được đọc. Chẩn đoán thường nhắc rằng package nằm trong module `library.core` nhưng `consumer.app` không đọc module đó.

Điểm cần nhớ: package có `exports` vẫn chưa đủ. Module sử dụng cần **readability** đến module cung cấp. Đặt module lên module path giúp hệ thống tìm kiếm module, nhưng không tự động làm mọi named module đọc được nhau.

### 4.2. Module đọc được nhau nhưng package không được export

Giữ `requires library.core;`, sửa descriptor thư viện:

~~~java
module library.core {
    // Không exports org.example.library.api
}
~~~

Khi `Main` cố `import Greeting`, javac thường báo lỗi dạng:

~~~text
package org.example.library.api is not visible
(package org.example.library.api is declared in module library.core,
 which does not export it)
~~~

Vì package chưa export, việc `Greeting` được khai báo `public` không giải quyết được lỗi.

Tình huống này xảy ra nhiều khi người viết thư viện nhầm tưởng rằng mọi `public class` trong một JAR đều đương nhiên là public API của named module.

### 4.3. Package đã export nhưng top-level type không public

Giữ `exports org.example.library.api;`, nhưng đổi khai báo:

~~~java
package org.example.library.api;

final class Greeting {
    // Package-private type.
}
~~~

Khi đó `Greeting` chỉ có quyền package-private theo ngôn ngữ Java. Module khác không thể dùng nó trực tiếp dù package được export.

Vì vậy `exports` không nâng một type package-private lên `public` và không nâng quyền thành viên `private` hay package-private.

### 4.4. Có đủ quyền truy cập class nhưng không đủ quyền gọi thành viên

Ví dụ:

~~~java
package org.example.library.api;

public class Counter {
    private int value;

    Counter() {             // constructor package-private
    }

    void increment() {      // method package-private
        value++;
    }

    public int current() {
        return value;
    }
}
~~~

Module khác có thể tham chiếu đến type `Counter` nếu ba điều kiện ở mục 2 thỏa, nhưng **không thể** gọi `new Counter()` từ package khác, không thể gọi `increment()` và không thể truy cập `value` trực tiếp. Khả năng truy cập type và khả năng gọi từng member là hai câu hỏi khác nhau.

## 5. Ma trận quyết định quyền access

| Module tiêu thụ đọc được module cung cấp? | Package export tới module tiêu thụ? | Top-level type public? | Truy cập type trực tiếp? |
|---|---|---|---|
| Có | Có | Có | Có, nếu các điều kiện Java khác cũng hợp lệ |
| Không | Có | Có | Không |
| Có | Không | Có | Không |
| Có | Có | Không | Không, nếu gọi từ package khác |
| Có | Chỉ export tới module khác | Có | Không |
| Có | Có | Có, nhưng member cần gọi là private | Type có thể truy cập; member đó không |

Bảng này giả định mã sử dụng nằm ở **một named module khác**. Các trường hợp diễn giải cùng module hoặc reflection không nên áp dụng máy móc kết luận của bảng.

## 6. Export không giới hạn và qualified exports

Mở cho mọi module có khả năng đọc module cung cấp:

~~~java
module library.core {
    exports org.example.library.api;
}
~~~

Mở cho đúng một hoặc một số named module được chỉ định:

~~~java
module library.core {
    exports org.example.library.api to consumer.app, admin.tool;
}
~~~

Ý nghĩa của dạng thứ hai:

- `consumer.app` và `admin.tool` có thể sử dụng những type accessible ở package `api` nếu chúng đọc được `library.core`.
- Các named module khác không được quyền truy cập trực tiếp package `api` nhờ khai báo này.
- Tên sau `to` là **tên module**, không phải package hay tên class.
- Qualified export không tự tạo `requires` ở phía tiêu thụ; mỗi module nhận quyền vẫn cần quan hệ đọc phù hợp.

Dạng qualified export hữu ích với API chỉ dành cho công cụ quản trị hoặc một module tích hợp đã xác định. Nhưng nếu đó là API dùng chung cho nhiều ứng dụng độc lập, `exports p;` thường rõ ràng và dễ duy trì hơn.

## 7. `requires`, `requires transitive` và cách truyền readability

Thông thường:

~~~java
module consumer.app {
    requires library.core;
}
~~~

Nghĩa là `consumer.app` đọc `library.core`. Tuy nhiên, quan hệ đọc có thể được hình thành gián tiếp.

Giả sử có ba module:

~~~text
app.frontend --> service.facade --> model.api
~~~

Nếu `service.facade` khai báo:

~~~java
module service.facade {
    requires transitive model.api;
    exports example.service;
}
~~~

Và `app.frontend` khai báo:

~~~java
module app.frontend {
    requires service.facade;
}
~~~

Thì `app.frontend` cũng đọc được `model.api` nhờ `requires transitive`. Đây là cơ chế phù hợp khi public API của facade dùng các kiểu công khai từ module `model.api`.

Nhưng **readability được truyền không đồng nghĩa exports được truyền**: package chứa type trong `model.api` vẫn phải được export tới `app.frontend`. Nếu package chỉ export cho một module khác, `requires transitive` không mở được package đó cho ứng dụng.

Một số lưu ý:

- Mọi named module đều đọc module `java.base` theo mặc định; không cần `requires java.base;`.
- `requires static` là dependency bắt buộc lúc biên dịch nhưng có thể không hiện diện khi chạy. Nó không là cách bỏ qua giới hạn exports và cần cân nhắc trước khi dùng kiểu của dependency trong đường chạy thực tế.
- `requires` chỉ là khai báo quan hệ đọc. Nó không thay đổi `public`, `protected`, `private` hay exports của module đích.

## 8. Nested type, interface, record, enum và API signature

Quy tắc JPMS không chỉ áp dụng cho `class`. Một `public interface`, `public enum`, `public record` hoặc `public @interface` trong package không export cũng không tự động accessible từ module khác.

Với **nested type**, cần quan tâm cả lớp bao ngoài:

~~~java
package org.example.library.api;

public class Container {
    public static class Nested {
        public static String value() {
            return "OK";
        }
    }
}
~~~

Nếu package được export và consumer đọc được module cung cấp, `Container.Nested` có thể được sử dụng theo luật Java thông thường. Ngược lại:

~~~java
package org.example.library.api;

class Container {
    public static class Nested {
    }
}
~~~

`Nested` dù có `public` vẫn không trở thành một type bên ngoài có thể dùng theo tên `Container.Nested`: lớp bao ngoài `Container` không accessible.

Với API public chứa tham số hoặc kiểu trả về từ package không export, người tiêu thụ có thể gặp lỗi khi sử dụng API:

~~~java
// Package: org.example.library.api, được exports
package org.example.library.api;

import org.example.library.internal.TextFormatter;

public interface FormatterFactory {
    TextFormatter create();
}
~~~

Điều đó làm hợp đồng công khai bị phụ thuộc vào kiểu nội bộ không accessible. Người thiết kế module nên đặt kiểu giao diện hoặc DTO phù hợp vào package API:

~~~java
// Package: org.example.library.api
package org.example.library.api;

public interface Formatter {
    String format(String input);
}
~~~

~~~java
// Package: org.example.library.api
package org.example.library.api;

public final class Formatters {
    private Formatters() {}

    public static Formatter greeting() {
        return input -> "Hello, " + input;
    }
}
~~~

Mã ngoài module chỉ cần nhìn thấy `Formatter` và `Formatters`. Chi tiết triển khai có thể nằm trong package không export.

## 9. `exports` khác `opens` ra sao?

Đây là điểm thường gây nhầm lẫn khi thảo luận về “access”:

- `exports p;` cho phép truy cập thông thường, cả compile time và runtime, tới những public type và public member accessible trong package `p`, tùy readability và luật Java.
- `opens p;` mở package `p` cho **reflection ở runtime**, bao gồm deep reflection khi hợp lệ. Nó không tạo quyền `import` kiểu trong mã Java từ module khác.
- `opens p to framework.module;` chỉ mở package cho module được chỉ định.
- `open module x { ... }` mở các package để hỗ trợ reflection ở runtime; điều đó không đồng nghĩa xuất tất cả package cho truy cập mã nguồn thông thường.

Ví dụ:

~~~java
module library.core {
    exports org.example.library.api;
    opens org.example.library.internal to reflection.tool;
}
~~~

`consumer.app` không thể sử dụng câu lệnh `import org.example.library.internal.TextFormatter;` chỉ vì package `internal` được mở cho `reflection.tool`. Ngay cả `reflection.tool`, với khai báo `opens` đó, cũng không nhận quyền import thông thường chỉ từ `opens`.

Khi gặp `InaccessibleObjectException` do deep reflection, kiểm tra `opens`. Khi gặp lỗi compile do type trong package không visible, kiểm tra `requires` và `exports`. Hai loại sự cố có cơ chế xử lý khác nhau.

## 10. Kiểm tra readability và exports ở runtime

Có thể dùng API `java.lang.Module` để quan sát module sở hữu type và quan hệ giữa các module. Đặt đoạn dưới đây trong phương thức `main` của ví dụ đang hoạt động:

~~~java
Module consumer = Main.class.getModule();
Module provider = Greeting.class.getModule();

System.out.println(consumer.getName());
System.out.println(provider.getName());
System.out.println(consumer.canRead(provider));
System.out.println(
    provider.isExported("org.example.library.api", consumer)
);
System.out.println(
    provider.isExported("org.example.library.internal", consumer)
);
~~~

Với descriptor ban đầu ở mục 3, kết quả tương ứng là:

~~~text
consumer.app
library.core
true
true
false
~~~

`canRead` trả lời câu hỏi **module consumer đọc được provider không?** `isExported(packageName, consumer)` trả lời câu hỏi **package đó được export tới consumer không?** Hai phương thức này không thay việc kiểm tra quyền `public`/package-private của từng type hay member.

Cũng có thể xem descriptor đã biên dịch bằng JDK:

~~~shell
java --module-path out --describe-module library.core
~~~

Trong đầu ra, quan sát các package được export và những package chỉ được chứa bên trong module.

## 11. Trường hợp module tự động và unnamed module

Ba điều kiện trên dễ thấy nhất khi cả bên cung cấp lẫn bên sử dụng đều là **explicit named modules**. Trong thực tế, cần phân biệt thêm:

**Automatic module.** Một JAR nằm trên module path nhưng không có `module-info.class` có thể được xử lý như automatic module. Automatic module có quy tắc đặc biệt: nhìn chung các package của nó được export, và nó đọc được các module khác theo cơ chế automatic module. Điều này hỗ trợ chuyển tiếp từ thư viện cũ, nhưng không thể giả định mọi thuộc tính của explicit named module đều giống automatic module.

**Unnamed module (classpath).** Mã đặt trên classpath thuộc unnamed module và có cơ chế readability riêng. Khi muốn mã đó truy cập một package nội bộ của **named module**, yêu cầu export vẫn có ý nghĩa; một package không export không bỗng trở thành public API chỉ vì caller chạy trên classpath.

**Cùng module.** Với hai package thuộc cùng một named module, khai báo `exports` không cần thiết cho việc một class `public` của package này được class ở package kia sử dụng. Luật truy cập Java vẫn áp dụng. Ranh giới `exports` đặc biệt quan trọng khi **đi qua biên giới module**.

Nhờ các trường hợp này, khi chẩn đoán lỗi trước hết nên xác định: class đang chạy ở module nào, đó là explicit named, automatic hay unnamed module và quá trình chạy đặt JAR ở module path hay classpath.

## 12. Các cờ bổ sung quyền khi cần di trú

Có trường hợp công cụ cũ hoặc bài kiểm thử cần truy cập một package vốn không export. JDK cung cấp các tùy chọn để bổ sung quan hệ đọc hoặc quyền truy cập mà không sửa descriptor gốc.

**`--add-reads`**: thêm quan hệ đọc, ví dụ:

~~~shell
java --add-reads consumer.app=library.core --module-path out -m consumer.app/org.example.app.Main
~~~

Cờ này chỉ giải quyết readability. Nếu package chưa export cho consumer, cờ trên vẫn chưa đủ.

**`--add-exports`**: export bổ sung một package cho module cụ thể. Với biến thể `Main` trực tiếp import `TextFormatter`, cần cấu hình thích hợp lúc biên dịch và chạy:

~~~shell
javac --module-source-path src -d out -m library.core,consumer.app --add-exports library.core/org.example.library.internal=consumer.app
java --module-path out --add-exports library.core/org.example.library.internal=consumer.app -m consumer.app/org.example.app.Main
~~~

Ví dụ chỉ dùng khi bạn đã sửa `Main` để gọi trực tiếp type nội bộ và đang thử nghiệm hành vi. Trong ứng dụng thực tế, đặt các tùy chọn compiler/JVM đúng theo công cụ build đang sử dụng.

**`--add-opens`**: bổ sung quyền mở package cho deep reflection lúc chạy:

~~~shell
java --module-path out --add-opens library.core/org.example.library.internal=consumer.app -m consumer.app/org.example.app.Main
~~~

`--add-opens` không thay thế `--add-exports` cho quyền import ở compile time.

Với mã trên classpath, một mục tiêu thường gặp của `--add-exports` hoặc `--add-opens` là `ALL-UNNAMED`. Các cờ này chủ yếu hữu ích cho tương thích, kiểm thử hoặc di trú. API ổn định nên được thể hiện trong `module-info.java` và thiết kế package thay vì yêu cầu ứng dụng phụ thuộc lâu dài vào những ngoại lệ.

## 13. Những lỗi phổ biến và cách xác định nguyên nhân

### `package ... is not visible`

Có thể do module caller không đọc được module sở hữu package hoặc package không được export cho caller. Đọc kỹ phần giải thích kèm lỗi để phân biệt nguyên nhân.

Cách xử lý: kiểm tra `requires`, tên module, tên package, `exports` và giới hạn `exports ... to`.

### `cannot find symbol`

Có thể do sai tên type/import, thiếu class trong bản build, thay đổi API hoặc lỗi cấu hình nguồn. Không nên quy mọi `cannot find symbol` thành lỗi exports.

Cách xử lý: xác minh class tồn tại trong artifact đang biên dịch và package/type name đúng.

### `module not found`

Module cung cấp chưa được tìm thấy trong đường tìm kiếm module hoặc tên `requires` không khớp với tên module.

Cách xử lý: kiểm tra `--module-path`, tên module trong descriptor hay metadata của JAR, và cấu hình build.

### `IllegalAccessError`

Có thể xuất hiện lúc runtime nếu bytecode đang tham chiếu đến class/member mà quyền truy cập hiện tại không cho phép, chẳng hạn khi cấu hình module dùng lúc build và lúc chạy khác nhau.

Cách xử lý: đối chiếu module graph và quyền export của đúng phiên bản đang chạy.

### `InaccessibleObjectException` khi reflection

Thường liên quan đến deep reflection vào package chưa mở cho module thực hiện reflection.

Cách xử lý: xem xét `opens`, `opens ... to` hoặc một ngoại lệ runtime có kiểm soát bằng `--add-opens`.

Lưu ý thêm: JPMS kiểm tra khả năng truy cập theo **module/package**, nhưng còn có các lỗi độc lập như split packages, xung đột dependency, thiếu module được resolve hoặc sai phiên bản lớp. Hãy dùng chẩn đoán thực tế để xác định đúng tầng lỗi.

## 14. Quy trình kiểm tra nhanh cho một type cụ thể

Khi được hỏi “Vì sao `SomeType` không access được từ module này?”, có thể thực hiện lần lượt:

1. **Xác định type đầy đủ:** ví dụ `org.example.library.api.Greeting` và module chứa nó.
2. **Xác định caller:** class đang nằm trong named module nào? Nếu chạy trên classpath, có phải unnamed module không?
3. **Kiểm tra module resolution/readability:** module caller có thể đọc module chứa type không? Nếu là named module, xem `requires` và `requires transitive`.
4. **Kiểm tra đúng package:** module cung cấp có `exports` package đó cho caller không? Qualified export có liệt kê đúng tên module caller không?
5. **Kiểm tra luật Java:** type có `public` không? Nếu nested type, enclosing types có accessible không? Constructor/member cần dùng có accessible không?
6. **Phân biệt cách truy cập:** dùng import/bytecode thông thường hay reflection? Với deep reflection, xem xét `opens` riêng.
7. **Kiểm tra cấu hình build và runtime:** có đang dùng phiên bản module khác hoặc các cờ `--add-reads`, `--add-exports`, `--add-opens` khác nhau không?

Có thể ghi nhớ ba câu hỏi để phân tích nhanh:

~~~text
WHO CAN READ?   consumer.canRead(provider)
WHICH PACKAGE?  provider.isExported(packageName, consumer)
WHICH MEMBER?   public/protected/package-private/private theo Java
~~~

## 15. Bài tập tự kiểm tra

**Bài 1.** Module `catalog.data` export `example.catalog.api`. Trong package này có `public class Product`. `checkout.app` có `requires catalog.data;`. Có thể import `Product` không?

**Đáp án:** Có, nếu class ở vị trí và cấu hình biên dịch hợp lệ. Cả readability, exports và access modifier đều thỏa.

**Bài 2.** Trong cùng module `catalog.data`, package `example.catalog.impl` chứa `public class SqlProductRepository` nhưng package không export. `checkout.app` có import được class này không?

**Đáp án:** Không. `public` không thay thế được việc export package qua biên giới named module.

**Bài 3.** Module `catalog.data` khai báo `exports example.catalog.impl to catalog.admin;`. `checkout.app` có được import `SqlProductRepository` không?

**Đáp án:** Không; quyền export chỉ cấp cho `catalog.admin`. Nếu `catalog.admin` muốn dùng type đó, nó vẫn phải đọc `catalog.data` và đáp ứng luật Java.

**Bài 4.** Trong package đã export, một `public class X` có constructor `private X()`. Module tiêu thụ có gọi `new X()` được không?

**Đáp án:** Không. Type `X` có thể accessible, nhưng constructor `private` không accessible với caller ngoài class.

**Bài 5.** `client.app` đọc `facade.api`; `facade.api` khai báo `requires transitive model.types;`. `model.types` không export `model.internal`. `client.app` có import public type từ `model.internal` không?

**Đáp án:** Không. `requires transitive` hỗ trợ readability, không thay đổi package exports của `model.types`.

**Bài 6.** Nếu thêm `opens example.catalog.impl to checkout.app;`, ứng dụng có quyền import các public class từ package đó không?

**Đáp án:** Không. `opens` dành cho reflection ở runtime, không cấp quyền truy cập mã nguồn thông thường.

## 16. Kết luận kiến thức

- Khi hai bên là **named modules**, một public type muốn được tham chiếu trực tiếp từ module khác cần: **module caller đọc được module cung cấp; package chứa type được export tới caller; type accessible theo luật Java**.
- `exports` làm lộ các type accessible trong **đúng package được khai báo**; nó không tự mở package con và không thay đổi access modifier.
- `requires transitive` chuyển tiếp quan hệ đọc; `exports ... to` giới hạn module được cấp quyền; `opens` phục vụ reflection ở runtime.
- Truy cập được type không có nghĩa truy cập được mọi constructor, method hay field của type.
- Khi thiết kế thư viện, export các package API ổn định, giữ package triển khai nội bộ không export và tránh để các type nội bộ xuất hiện trong hợp đồng công khai.
