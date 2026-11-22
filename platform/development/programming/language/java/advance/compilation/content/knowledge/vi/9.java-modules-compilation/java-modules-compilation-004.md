# requires transitive, requires static và ảnh hưởng khi biên dịch

Trong **Java Platform Module System (JPMS)**, mỗi named module có tệp `module-info.java` để khai báo quan hệ phụ thuộc, những package được cung cấp và những quyền truy cập cần thiết. Khi một module viết `requires other.module;`, điều đó không chỉ giúp trình biên dịch tìm JAR: nó góp phần xác định **đồ thị phụ thuộc** (*module graph*) và **quan hệ đọc module** (*readability*) của ứng dụng.

Hai bộ sửa đổi `transitive` và `static` trả lời **hai câu hỏi khác nhau**:

- **`requires transitive`:** khi module A đọc module B, và B khai báo phụ thuộc bắc cầu tới C, thì A cũng được **đọc C**. Nó phục vụ tính khả dụng của API được phơi ra qua các module.
- **`requires static`:** phụ thuộc được yêu cầu **khi biên dịch**, nhưng có thể **không hiện diện khi chạy**. Nó phục vụ dependency tùy chọn; điều đó không tự bảo đảm mọi đường thực thi vẫn hoạt động khi dependency bị thiếu.

Có thể kết hợp cả hai: `requires static transitive module.name;`. Khi ấy, ý nghĩa *transitive* áp dụng cho việc đọc dependency qua module khác, còn *static* quy định dependency được yêu cầu ở compile time nhưng có thể vắng mặt ở runtime. Trong bài này, chúng ta phân biệt rõ **phân giải module**, **readability**, **exports** và **thực thi các đoạn mã thực sự sử dụng module tùy chọn**.

Bài thực hành sử dụng **Java 17+**, có thể biên dịch bằng JDK 21 với `--release 17`. Mã nguồn và lệnh được đưa ra đầy đủ để tạo riêng từng ví dụ; không phải pseudocode.

## 1. Nhắc lại mô hình JPMS

Một module có cấu trúc cơ bản như sau:

```text
src/
  my.module/
    module-info.java
    my/
      package/
        SomeClass.java
```

Trong `module-info.java`, bạn có thể viết:

```java
module my.module {
    requires java.logging;
    exports my.package;
}
```

Ý nghĩa:

- `module my.module`: tên module hiện tại. Tên module trong ví dụ phải khớp tên thư mục module trên `--module-source-path`.
- `requires java.logging`: module hiện tại đọc `java.logging` và có phụ thuộc đối với module này.
- `exports my.package`: cho phép module khác, nếu **đọc được `my.module`**, truy cập các type `public` đủ điều kiện trong package `my.package`.
- `java.base` được mọi named module đọc ngầm định theo quy tắc ngôn ngữ; thường không phải khai báo `requires java.base;`.

Hai kiểm tra độc lập để một module A sử dụng type `public p.Type` thuộc module B là:

1. **A có đọc được B không?** Tức quan hệ readability trong module graph có cho phép A truy cập B.
2. **B có export package `p` cho A không?** Nếu B không export package ấy (hoặc export có điều kiện nhưng không cho A), type không thể được truy cập thông thường từ A.

`requires transitive` chỉ giải quyết **quan hệ đọc module**, không tự động export mọi package của module phụ thuộc. `requires static` giải quyết **tính bắt buộc theo giai đoạn**, không tự động tải hay nạp mọi class ở runtime.

### Bốn dạng requires cần nhớ

| Khai báo trong module B | B đọc C khi biên dịch? | C bắt buộc khi chạy? | Module A đọc B có tự đọc C? |
| --- | --- | --- | --- |
| `requires C;` | Có | Có, theo module resolution thông thường | Không chỉ vì A đọc B |
| `requires transitive C;` | Có | Có | **Có**, qua quan hệ bắc cầu |
| `requires static C;` | Có | **Không bắt buộc** | Không chỉ vì A đọc B |
| `requires static transitive C;` | Có | **Không bắt buộc** | **Có ở compile time**; tại runtime chỉ khi C được resolve phù hợp |

Trong bảng trên, “bắt buộc khi chạy” nói về phụ thuộc được module resolver yêu cầu để cấu hình module hợp lệ; không có nghĩa mọi class trong module bắt buộc được nạp ngay. `static` đánh dấu optional resolution tại runtime, chứ không sửa nguyên lý **thiếu class được dùng thực sự vẫn có thể lỗi**.

## 2. requires: module phụ thuộc đọc được module kia, nhưng không truyền tự động

Giả sử có ba module:

```text
learn.app  --->  learn.api  --->  learn.model
```

Nếu `learn.app` khai báo `requires learn.api;`, còn `learn.api` chỉ khai báo `requires learn.model;`, thì:

- `learn.api` đọc `learn.model` để biên dịch phần code của chính nó.
- `learn.app` đọc `learn.api` vì nó khai báo dependency này.
- `learn.app` **không tự có readability đối với `learn.model`**, dù `learn.api` đang dùng nó.

Đây là chủ đích của hệ thống module: quan hệ phụ thuộc là một phần API được khai báo. Muốn ứng dụng tự truy cập type của `learn.model`, ứng dụng hoặc cần `requires learn.model;` trực tiếp, hoặc module API cần công bố phụ thuộc bằng `requires transitive learn.model;` khi điều đó đúng với thiết kế API.

### Vì sao lỗi thường chỉ xuất hiện khi đổi sang named modules?

Trên classpath truyền thống, nhiều JAR cùng được đặt vào một không gian tìm kiếm tương đối phẳng. Khi chuyển sang module path, compiler kiểm tra **module readability và exports**. Việc một JAR hiện diện trên ổ đĩa hoặc một module nằm trong module path **không đồng nghĩa** code ở mọi module đều được quyền import type của nó.

Lỗi điển hình khi thiếu readability có nội dung tương tự:

```text
package learn.model is not visible
(package learn.model is declared in module learn.model, but module learn.app does not read it)
```

Dòng diagnostic thực tế có thể có file, dòng, vị trí và cách diễn đạt khác tùy phiên bản compiler. Đừng sửa bằng cách chuyển mọi thứ trở lại classpath trước khi hiểu module graph.

## 3. Thực hành số 1: requires transitive làm lộ dependency trong API

Ta tạo ba named modules, trong đó API trả về một type khai báo ở module khác.

### 3.1. Cây thư mục

Tạo các file theo đúng cấu trúc:

```text
transitive-lab/
  src/
    learn.model/
      module-info.java
      learn/model/Message.java
    learn.api/
      module-info.java
      learn/api/Greeter.java
    learn.app/
      module-info.java
      learn/app/Main.java
```

Ở thư mục gốc `transitive-lab`, tạo `src/learn.model/module-info.java`:

```java
module learn.model {
    exports learn.model;
}
```

Tạo `src/learn.model/learn/model/Message.java`:

```java
package learn.model;

public record Message(String text) {}
```

`record` được hỗ trợ trong Java 17. Package `learn.model` phải được **export** để module tiêu thụ có thể dùng `Message`.

Tạo `src/learn.api/module-info.java`:

```java
module learn.api {
    requires transitive learn.model;
    exports learn.api;
}
```

Tạo `src/learn.api/learn/api/Greeter.java`:

```java
package learn.api;

import learn.model.Message;

public class Greeter {
    public static Message message() {
        return new Message("hello");
    }
}
```

Điểm thiết kế: `Greeter.message()` **trả về `learn.model.Message`**, nên `learn.model` là một phần bề mặt API được client nhìn thấy. `requires transitive learn.model;` giúp người dùng `learn.api` đọc module chứa kiểu công khai đó.

Tạo `src/learn.app/module-info.java`:

```java
module learn.app {
    requires learn.api;
}
```

Cuối cùng, tạo `src/learn.app/learn/app/Main.java`:

```java
package learn.app;

import learn.api.Greeter;
import learn.model.Message;

public class Main {
    public static void main(String[] args) {
        Message message = Greeter.message();
        System.out.println(message.text());
    }
}
```

**Quan sát:** `learn.app` không khai báo `requires learn.model;`, nhưng được import `Message` vì `learn.api` công khai phụ thuộc bằng `requires transitive learn.model;` và `learn.model` export package tương ứng.

### 3.2. Biên dịch và chạy

Đứng tại thư mục gốc `transitive-lab`. Để tránh phụ thuộc vào cú pháp glob của hệ điều hành, lệnh sau liệt kê đủ sáu file nguồn:

```bash
javac --release 17 --module-source-path src -d mods src/learn.model/module-info.java src/learn.model/learn/model/Message.java src/learn.api/module-info.java src/learn.api/learn/api/Greeter.java src/learn.app/module-info.java src/learn.app/learn/app/Main.java
java --module-path mods -m learn.app/learn.app.Main
```

Stdout chính xác:

```text
hello
```

Cùng hai lệnh trên hoạt động trong Bash, zsh, Windows PowerShell và cmd khi viết **mỗi lệnh trên một dòng** và đường dẫn tương đối đúng như cây thư mục. Trên Windows, Java cũng chấp nhận dấu gạch chéo `/` trong phần lớn tham số đường dẫn mô tả ở đây. Compiler tạo thư mục `mods/learn.model`, `mods/learn.api` và `mods/learn.app`, mỗi thư mục chứa các class file của module tương ứng.

`--module-source-path src` nói với `javac` cách bố trí mã nguồn theo named modules. `-d mods` quy định nơi phát sinh class file. `--module-path mods` đưa các module đã biên dịch vào tầm nhìn của Java launcher. `-m learn.app/learn.app.Main` chọn entry module và main class.

### 3.3. Bỏ transitive sẽ ra sao?

Chỉ sửa file `src/learn.api/module-info.java` thành:

```java
module learn.api {
    requires learn.model;
    exports learn.api;
}
```

Sau đó **biên dịch lại toàn bộ sáu file bằng đúng lệnh `javac` ở mục 3.2** (có thể dùng một thư mục output mới như `mods-plain` và đổi `-d` tương ứng cho chắc chắn). Compiler báo lỗi cho `learn.app` tại chỗ import `learn.model.Message`, vì `learn.app` **không đọc `learn.model`**. Lỗi có thông điệp tương tự:

```text
package learn.model is not visible
(module learn.app does not read module learn.model)
```

Đây là **lỗi compile time có chủ đích**: `learn.api` vẫn biên dịch được với `Message`, nhưng `learn.app` không được kế thừa quyền đọc qua một `requires` thông thường.

Có hai cách giải quyết tùy chủ đích API:

1. **Phục hồi `requires transitive learn.model;`** trong `learn.api` khi `Message` thực sự là một phần API công khai của `Greeter`.
2. Hoặc thêm `requires learn.model;` vào `learn.app/module-info.java` nếu client chủ đích phụ thuộc trực tiếp vào model và bạn muốn hợp đồng dependency tường minh tại client.

Không thể giải quyết thiếu readability bằng cách chỉ thêm `exports learn.model;` nếu lệnh `exports` đã có sẵn: module có export package nhưng client vẫn phải **đọc được module**.

### 3.4. Suy ra đồ thị readability

Với `learn.api` khai báo `requires transitive learn.model;`:

```text
learn.app  --requires-->  learn.api
    |                         |
    |--reads implied----------+--requires transitive--> learn.model
```

Mục đích không phải “tự động đưa mọi JAR phụ thuộc vào ứng dụng”. `transitive` mô tả **đường đọc module**; module vẫn phải hiện diện/được resolve phù hợp, class được truy cập vẫn phải `public` và package vẫn phải export.

### Khi nào nên chọn requires transitive?

Chọn `requires transitive` khi API công khai của module hiện tại **phụ thuộc type thuộc module kia**: type trả về, type tham số, superclass/interface công khai hoặc generic API mà client dự kiến thao tác. Không dùng `transitive` cho mọi dependency nội bộ; khai báo tràn lan làm đồ thị module lộ nhiều quan hệ và giảm tính rõ ràng của ranh giới API.

Nếu `Greeter` chỉ trả về `String` và dùng `Message` hoàn toàn bên trong implementation, `requires learn.model;` thường đủ: client không cần trực tiếp đọc module model chỉ để gọi API trả chuỗi. Tuy nhiên, lựa chọn cuối cùng phụ thuộc mục tiêu API và phạm vi các type mà client thực sự cần.

## 4. requires static: compile-time bắt buộc, runtime có thể tùy chọn

`requires static optional.module;` được hiểu như sau:

- **Khi biên dịch module khai báo:** compiler cần thấy named module được yêu cầu; code của module khai báo có thể sử dụng type được export từ dependency đó.
- **Khi chạy:** module khai báo có thể được resolve mà module tùy chọn không hiện diện. Việc app không dùng tới type của dependency trong đường thực thi đó có thể cho phép nó chạy thành công.
- **Nếu code thực sự cố nạp/dùng type bị thiếu:** lỗi runtime vẫn có thể xảy ra, như `NoClassDefFoundError` hoặc lỗi liên quan tùy vị trí tham chiếu. `static` không tạo một “dummy implementation” và không biến mọi API thành optional-safe.

Tên `static` trong chỉ thị module **không liên quan đến modifier `static` của field/method**. Nó là một loại phụ thuộc theo **thời điểm cần có module**.

Ví dụ điển hình là module có tính năng mở rộng tùy chọn: lúc build cần API để compiler kiểm tra kiểu, nhưng khi triển khai “chế độ cơ bản” không cần plugin thư viện đó. Thiết kế phải tránh kích hoạt code dùng plugin khi nó vắng mặt.

## 5. Thực hành số 2: requires static và module runtime tùy chọn

Thực hành này tạo **ba module độc lập** với ví dụ trước; dùng một thư mục mới `static-lab` để tránh trùng tên module hoặc class.

### 5.1. Cấu trúc và mã nguồn

```text
static-lab/
  src/
    learn.optional/
      module-info.java
      learn/optional/OptionalText.java
    learn.feature/
      module-info.java
      learn/feature/Feature.java
    learn.host/
      module-info.java
      learn/host/Main.java
```

Tệp `src/learn.optional/module-info.java`:

```java
module learn.optional {
    exports learn.optional;
}
```

Tệp `src/learn.optional/learn/optional/OptionalText.java`:

```java
package learn.optional;

public class OptionalText {
    public static String value() {
        return "optional works";
    }
}
```

Tệp `src/learn.feature/module-info.java`:

```java
module learn.feature {
    requires static learn.optional;
    exports learn.feature;
}
```

Tệp `src/learn.feature/learn/feature/Feature.java`:

```java
package learn.feature;

import learn.optional.OptionalText;

public class Feature {
    public static String safe() {
        return "core works";
    }

    public static String optional() {
        return OptionalText.value();
    }
}
```

Tệp `src/learn.host/module-info.java`:

```java
module learn.host {
    requires learn.feature;
}
```

Tệp `src/learn.host/learn/host/Main.java`:

```java
package learn.host;

import learn.feature.Feature;

public class Main {
    public static void main(String[] args) {
        System.out.println(Feature.safe());
        if (args.length > 0) {
            System.out.println(Feature.optional());
        }
    }
}
```

`Main` gọi `Feature.optional()` **chỉ khi** có đối số dòng lệnh. Điều đó giúp tách đường thực thi an toàn và đường thực thi cần dependency tùy chọn.

### 5.2. Biên dịch đủ ba module

Tại thư mục `static-lab`:

```bash
javac --release 17 --module-source-path src -d mods src/learn.optional/module-info.java src/learn.optional/learn/optional/OptionalText.java src/learn.feature/module-info.java src/learn.feature/learn/feature/Feature.java src/learn.host/module-info.java src/learn.host/learn/host/Main.java
```

Tại compile time, module `learn.optional` **bắt buộc có trong vùng mà compiler có thể nhìn thấy**. Nhờ `requires static learn.optional;`, file `Feature.java` biên dịch được dù chứa tham chiếu đến `OptionalText`. Nếu loại hoàn toàn module optional khỏi nguồn và module path khi biên dịch lại `learn.feature`, quá trình biên dịch sẽ thất bại vì không tìm được dependency yêu cầu.

Đây chính là điểm khác biệt với runtime: `static` không có nghĩa dependency optional ở **cả hai** giai đoạn.

### 5.3. Chạy đường cơ bản

```bash
java --module-path mods -m learn.host/learn.host.Main
```

Stdout:

```text
core works
```

Chương trình không gọi `Feature.optional()`. Với `requires static`, `learn.optional` không mặc nhiên trở thành module được resolve trong runtime graph chỉ bởi khai báo `requires static` của `learn.feature`, ngay cả khi nó hiện diện trong thư mục `mods`.

Nếu muốn thử thực sự không phân phối module optional, có thể tạo một bản thư mục runtime chỉ chứa hai module `learn.feature` và `learn.host`, rồi dùng `--module-path` trỏ tới bản đó. Điều quan trọng là **giữ nguyên output đã biên dịch** và chạy bằng module path không có `learn.optional`; ví dụ vẫn in `core works`.

### 5.4. Chạy chức năng cần dependency: phải resolve module optional

Vẫn ở `static-lab`, chạy:

```bash
java --module-path mods --add-modules learn.optional -m learn.host/learn.host.Main use
```

Stdout chính xác:

```text
core works
optional works
```

`--add-modules learn.optional` làm `learn.optional` trở thành một root module bổ sung để runtime **resolve module**. Khi đã có module thực sự trong graph và package được export, `Feature.optional()` gọi được `OptionalText.value()`.

Thử không có `--add-modules` nhưng có đối số `use`:

```bash
java --module-path mods -m learn.host/learn.host.Main use
```

Trong cấu hình module cụ thể của ví dụ, chương trình in `core works` rồi ném lỗi dạng:

```text
java.lang.NoClassDefFoundError: learn/optional/OptionalText
```

Đây là **đoạn quan trọng của lỗi**; stack trace và nguyên nhân lồng nhau có thể khác theo JVM. Ta thấy một module có mặt **trên module path** vẫn chưa chắc **được resolve** vào graph. Vì vậy cần phân biệt “có file module”, “được resolve”, “đọc được” và “class đã được nạp”.

Nếu module tùy chọn hoàn toàn không có trên module path, lệnh `--add-modules learn.optional` lại không thể resolve module đó; phải cung cấp dependency thật trước. `--add-modules` không tự tải thư viện từ Internet.

### 5.5. Điều kiện để ứng dụng optional-safe thật sự

Ví dụ đơn giản dùng nhánh `if (args.length > 0)`. Ứng dụng thực tế có thể cần kiến trúc khác:

- Không để đường cơ bản khởi tạo class có static initializer đụng đến type vắng mặt.
- Không giả định mọi signature chứa type tùy chọn đều an toàn trong mọi nơi mà chúng được nạp, kiểm tra hoặc phản chiếu.
- Tách API cốt lõi khỏi integration module hoặc lớp adapter nếu dependency là tùy chọn nghiêm túc.
- Kiểm tra cả hai bản triển khai: **có dependency và không có dependency**, với những đường code thực tế mà deployment dùng.
- Nếu triển khai plugin theo cơ chế dịch vụ, có thể cân nhắc `ServiceLoader`/`uses`/`provides`, nhưng `requires static` không tự kích hoạt discovery.

**Lỗi như `NoClassDefFoundError` không phải một nhánh nghiệp vụ tùy chọn tốt.** Hãy thiết kế kiểm tra khả năng tích hợp và tách module phù hợp; đừng dùng lỗi liên kết class như cơ chế chọn chức năng thông thường.

## 6. Kết hợp requires static transitive

`transitive` và `static` là hai modifier hợp lệ của cùng chỉ thị `requires`, vì vậy có thể kết hợp:

```java
module learn.feature {
    requires static transitive learn.optional;
    exports learn.feature;
}
```

Về mặt biên dịch:

- `learn.feature` có thể sử dụng `learn.optional` nhờ dependency `static`.
- Một module khác đọc `learn.feature` sẽ được **readability tới `learn.optional` trong lúc biên dịch** nhờ `transitive`.
- Khả năng tham chiếu kiểu `public` vẫn phải tuân theo `exports` của module optional.

Về mặt runtime:

- Module optional **không bị bắt buộc phải có mặt chỉ vì `static transitive`**.
- Nếu optional có mặt và được resolve phù hợp, các quan hệ đọc có thể giúp code dùng type hoạt động.
- Nếu optional vắng mặt, đường code không đụng type đó có thể chạy; đường code phụ thuộc vào nó vẫn có thể lỗi khi class được dùng.

### 6.1. Thử đổi hai file trong static-lab

Sau khi chạy ví dụ trước, thay `src/learn.feature/module-info.java` bằng:

```java
module learn.feature {
    requires static transitive learn.optional;
    exports learn.feature;
}
```

Và thay `src/learn.host/learn/host/Main.java` bằng:

```java
package learn.host;

import learn.feature.Feature;
import learn.optional.OptionalText;

public class Main {
    public static void main(String[] args) {
        System.out.println(Feature.safe());
        if (args.length > 0) {
            System.out.println(OptionalText.value());
        }
    }
}
```

Lưu ý: `learn.host/module-info.java` **vẫn chỉ khai báo** `requires learn.feature;`. Code `learn.host` giờ import `learn.optional.OptionalText` trực tiếp mà không cần khai báo `requires learn.optional;`, vì nó nhận readability qua `requires static transitive` khi biên dịch.

Chạy lại lệnh biên dịch **đủ sáu file nguồn** ở mục 5.2. Lệnh này đã được kiểm tra thành công trên JDK 21 với `--release 17`.

Chạy không có đối số:

```bash
java --module-path mods -m learn.host/learn.host.Main
```

Stdout:

```text
core works
```

Chạy với module optional được thêm vào tập roots:

```bash
java --module-path mods --add-modules learn.optional -m learn.host/learn.host.Main use
```

Stdout:

```text
core works
optional works
```

Nếu bỏ `--add-modules` và vẫn thực thi nhánh dùng `OptionalText`, ví dụ có thể gặp lỗi class linkage tương tự. Đây là cách minh họa **static** và **transitive** tác động trên hai chiều khác nhau: thời điểm bắt buộc có module và khả năng client đọc module qua API.

Không nên dùng `requires static transitive` chỉ vì muốn “phòng mọi trường hợp”. Hãy dùng khi thư viện optional thực sự là một phần công khai của API, và có chiến lược runtime rõ ràng cho trường hợp nó vắng mặt. Nếu API cốt lõi không công khai type của dependency, `requires static` thông thường ít làm lộ quan hệ phụ thuộc hơn.

## 7. Bảng so sánh compile time và runtime theo ba góc nhìn

Giả sử A yêu cầu B, còn B có dependency C:

| B khai báo | C cần khi compile B? | A có thể dùng `public` type export từ C mà không `requires C`? | C bắt buộc khi runtime resolve B? |
| --- | --- | --- | --- |
| `requires C` | Có | Không; A thường phải `requires C` riêng | Có |
| `requires transitive C` | Có | Có, nếu C export package phù hợp | Có |
| `requires static C` | Có | Không; A thường phải `requires C` riêng | Không bắt buộc |
| `requires static transitive C` | Có | Có tại compile time, nếu C export package phù hợp | Không bắt buộc |

Lưu ý hai đối tượng điều khiển độc lập:

- **Readability** trả lời “code trong A có thể sử dụng type từ C không?”.
- **Module resolution** trả lời “C có thực sự nằm trong module graph hiện tại không?”.

Một module có trên `--module-path` chỉ là **observable**, chưa chắc là **resolved**. Một module đã được resolve vẫn phải có cạnh readability thích hợp để các type export của nó truy cập được trong mã của module khác.

### 7.1. exports và opens là hai quyền khác

`exports p;` dành cho **truy cập type public** từ module khác theo kiểm tra ngôn ngữ và runtime access. `opens p;` chủ yếu cấp quyền **deep reflection** đối với package khi điều kiện module phù hợp. Không thay `exports` bằng `opens` rồi mong compiler import `public p.Type` qua mọi module. `requires transitive` cũng không tạo `opens`, không cho phép phản chiếu tùy ý vào field private.

Ví dụ nếu `learn.model` không khai báo `exports learn.model;`, dù `learn.api` dùng `requires transitive learn.model;`, code `learn.app` vẫn không import `learn.model.Message` được theo truy cập module thông thường. **Readability cần đi cùng export**.

### 7.2. requires static không đồng nghĩa với static import

`requires static learn.optional;` trong `module-info.java` **khác hoàn toàn** `import static java.lang.Math.PI;` trong một file Java thường.

- `requires static`: dependency module có thể thiếu ở runtime.
- `import static`: chỉ giúp tham chiếu thành viên static bằng tên ngắn trong mã nguồn; không thay module readability và không làm dependency optional.

Đừng dùng từ “static” để suy luận có liên quan tới static initialization hoặc method dispatch trong trường hợp này.

## 8. Các lỗi phổ biến và cách nhận diện

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa phù hợp |
| --- | --- | --- |
| `package ... is not visible`, module A không đọc C | Thiếu `requires C` hoặc cần một cạnh `requires transitive C` trong B | Xem API surface; khai báo dependency tại đúng module |
| Compiler thấy package nhưng báo module không export | C không `exports` package cho A | Chỉ export phần API cần dùng, có cân nhắc ranh giới |
| `module not found: learn.optional` lúc compile | Dependency `requires static` vẫn phải có tại compile time | Cung cấp module optional vào source/module path của build |
| Chạy app thiếu module với `requires C` thông thường | Runtime module graph yêu cầu dependency | Cung cấp module C đúng phiên bản |
| Chạy với `requires static C` không lỗi dù C vắng | Không có đường thực thi nào buộc sử dụng C | Đây là optionality dự kiến; vẫn phải test các nhánh |
| Module nằm trong `mods` nhưng code optional vẫn lỗi | Module static dependency chưa được resolve hoặc class không hiện diện đúng | Xem `--add-modules`/roots, graph, module path và đường code |
| Gọi code optional ném `NoClassDefFoundError` | Type được tham chiếu nhưng không có class/module runtime đáp ứng | Đảm bảo module được resolve hoặc tránh dùng integration khi thiếu |
| Đã khai báo `requires transitive` mà vẫn không import được | Package chưa export, type không public, module path sai hoặc tên package không đúng | Kiểm tra cả exports, readability, access modifier và tên |
| Xóa dependency compile được nhưng runtime thất bại | Build có classpath/module path ẩn, version/runtime graph khác | Tái tạo build sạch và đối chiếu đồ thị module |
| Thêm dependency trên classpath mà JPMS không thấy | Code named module tìm dependency trên module path theo cấu hình khác | Dùng module path đúng và kiểm tra automatic module nếu cần |

**Không mặc nhiên đề xuất `--add-reads` hoặc `--add-exports` để “sửa cho biên dịch được”.** Các flag đó có thể hỗ trợ thử nghiệm hoặc migration, nhưng nếu source module descriptor sai hợp đồng thì sửa `module-info.java` và ranh giới API là hướng bền vững hơn.

## 9. Cách kiểm tra module graph thật

Ngoài đọc `module-info.java`, JDK có công cụ hỗ trợ xác minh.

### 9.1. Xem module đã biên dịch

Đối với các ví dụ đã có thư mục `mods`:

```bash
jar --describe-module --file mods/learn.api/module-info.class
```

Lệnh `jar --describe-module` thường dùng với một JAR file; đối với **exploded module** như `mods/learn.api`, dùng cú pháp đường dẫn module phù hợp của phiên bản công cụ hoặc kiểm tra trực tiếp `javap` như dưới đây. Cách đáng tin hơn để xem descriptor từ class file là:

```bash
javap -v mods/learn.api/module-info.class
```

Tìm các entry thuộc module descriptor, đặc biệt `requires transitive`. Với ví dụ `static-lab`, xem `mods/learn.feature/module-info.class` để xác định `requires static` hoặc `requires static transitive` sau khi biên dịch.

**Gợi ý:** đừng hiểu output của `javap` trên `module-info.class` như Java source được tái tạo nguyên xi; đó là thông tin class-file attributes, với các tên flag do tool hiển thị.

### 9.2. Quan sát runtime resolution

Với JDK hỗ trợ option hiển thị module resolution:

```bash
java --show-module-resolution --module-path mods -m learn.host/learn.host.Main
```

Đây là lệnh cho **static-lab**. Output có thể dài, phụ thuộc JDK và module được đưa vào graph. So sánh với:

```bash
java --show-module-resolution --module-path mods --add-modules learn.optional -m learn.host/learn.host.Main use
```

Lúc này có thể quan sát module optional được thêm vào roots. **Đừng giả định `--show-module-resolution` in cùng một thứ tự hay cùng số dòng** giữa các JDK.

Ngoài ra, `java --list-modules` liệt kê các **system modules** của runtime, không phải danh sách tất cả module JAR của một ứng dụng tùy ý trên module path. Để xem module thuộc đường dẫn ứng dụng, dùng đúng công cụ giải quyết graph/runtime như ví dụ, hoặc kiểm tra descriptor/JAR riêng.

### 9.3. jdeps cho phân tích phụ thuộc

`jdeps` là công cụ phân tích dependency tĩnh ở mức class/JAR/module. Nó có thể giúp nhận diện module phụ thuộc trong artifact, nhưng kết quả phụ thuộc cách đóng gói, các tùy chọn `--module-path` và các class được tham chiếu. `jdeps` không thể thay thế kiểm tra runtime của nhánh optional vì chỉ dựa trên phân tích tĩnh.

Để xem tùy chọn phù hợp với JDK:

```bash
jdeps --help
javac --help
java --help
```

## 10. Thiết kế API: khi nào transitive, khi nào static?

**Chọn `requires transitive` khi:**

- Một type từ dependency xuất hiện trực tiếp trong API công khai mà consumer sẽ dùng (return type, parameter, superclass/interface, generic signature).
- Module muốn chủ động biểu đạt rằng client đọc nó cũng cần đọc dependency đó.
- Dependency có mặt ở runtime và nằm trong module graph bình thường.

**Chọn `requires static` khi:**

- Compile cần type của dependency nhưng runtime có bản triển khai hoặc đường chạy không dùng dependency ấy.
- Việc thiếu dependency được kiểm soát bằng thiết kế API và kiểm thử, không dựa vào bắt ngoại lệ linkage làm flow chính.
- Đã xác định cách module optional sẽ được thêm vào runtime graph nếu cần.

**Chọn `requires static transitive` khi cả hai đều đúng:**

- API của module hiện tại phơi type thuộc một module tùy chọn cho client.
- Client cần readability ở compile time.
- Sản phẩm có chiến lược runtime có/không có optional module và các nhánh được tách đúng.

**Chọn `requires` thông thường khi:**

- Dependency cần thiết trong vận hành bình thường nhưng không phải một phần contract API mà client cần import trực tiếp.

Một sơ đồ lựa chọn nhanh:

```text
Dependency có thực sự cần ở runtime?
    |
    +-- Có --------------------> Code của client cần đọc type từ dependency
    |                                |
    |                                +-- Có  -> requires transitive
    |                                +-- Không -> requires
    |
    +-- Có thể vắng -----------> Client có cần đọc type từ dependency ở compile time?
                                     |
                                     +-- Có  -> requires static transitive
                                     +-- Không -> requires static
```

Sơ đồ này là **hướng dẫn thiết kế API**, không thay thế JLS hay các trường hợp đặc biệt như service binding, automatic modules, dynamic layers và reflection.

## 11. Bài tập có đáp án

### Bài 1: Đọc sơ đồ dependency

Cho:

```java
module alpha {
    requires beta;
}
module beta {
    requires transitive gamma;
}
module gamma {
    exports gamma.api;
}
```

Giả sử các descriptor hợp lệ và các module đều được cung cấp đúng, code trong `alpha` có thể import type `public` từ `gamma.api` không?

**Đáp án:** Có, vì `alpha` đọc `beta`, còn `beta` công bố `requires transitive gamma;`. Readability tới `gamma` được suy ra và `gamma.api` được export.

### Bài 2: Bỏ transitive

Đổi `beta` thành `requires gamma;` nhưng giữ `alpha` như cũ. Khi code `alpha` import `gamma.api.Point` thì sao?

**Đáp án:** Lỗi compile time vì `alpha` chưa có readability tới `gamma`. Sửa bằng `requires gamma;` trực tiếp trong `alpha`, hoặc khôi phục `requires transitive gamma;` ở `beta` nếu dependency thuộc API mà `beta` phơi ra.

### Bài 3: Module optional lúc chạy

```java
module feature {
    requires static plugin.api;
}
```

Có thể biên dịch `feature` khi hoàn toàn không cung cấp `plugin.api` không? Và chạy `feature` không có `plugin.api` được không?

**Đáp án:** Compiler **cần nhìn thấy `plugin.api`**; không có dependency thì biên dịch module khai báo yêu cầu thất bại. Runtime **có thể** chạy khi module optional vắng mặt, nếu không có đường code cần tới type của nó và các dependency bắt buộc khác được thỏa mãn.

### Bài 4: Optional module có mặt nhưng không resolve

Tại sao `java --module-path mods -m learn.host/learn.host.Main use` trong `static-lab` có thể lỗi dù `mods/learn.optional` tồn tại?

**Đáp án:** `requires static` không tự động yêu cầu runtime resolve optional module. Module path mô tả những module *có thể tìm được*, khác tập module thực sự đã resolve; ở ví dụ này cần thêm `--add-modules learn.optional` khi chạy nhánh `use`.

### Bài 5: requires static transitive

Một module `api` khai báo `requires static transitive types;`, còn `app` khai báo `requires api;`. Có phải `types` luôn được đóng gói và nạp khi app chạy không?

**Đáp án:** Không. Trong compilation, `app` được đọc `types` qua quan hệ bắc cầu khi dependency hiện diện. Lúc runtime, `types` không bị bắt buộc chỉ bởi `static`; phải cung cấp/resolve nếu code cần type đó.

### Bài 6: Exports và transitive

`api` có `requires transitive model;`, nhưng `model` không export `model.internal`. Client đọc `api` có thể import `model.internal.Secret` chỉ nhờ transitive không?

**Đáp án:** Không. Readability và export là hai điều kiện độc lập; type internal vẫn được đóng gói ở ranh giới module.

## 12. Tổng kết và tài liệu chính thống

Có thể ghi nhớ bằng hai câu hỏi khi đọc `module-info.java`:

1. **“Ai được đọc module này thông qua dependency?”** — `transitive` làm rõ quan hệ đọc bắc cầu, đặc biệt cho API dùng type từ module khác.
2. **“Khi nào dependency bắt buộc phải có?”** — `static` đặt dependency ở mức bắt buộc khi biên dịch nhưng cho phép vắng mặt khi chạy.

Khi kết hợp `requires static transitive`, hai thuộc tính cùng tồn tại: đọc bắc cầu **để compile**, optional **khi runtime**. Muốn code thực sự sử dụng class optional lúc chạy, module phải hiện diện và được resolve; phần API vẫn phải được `exports`.

Nguồn chính thống:

- [Java Language Specification SE 21 — `7.7.1 Dependences](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.1): ngữ nghĩa `requires`, `transitive` và `static`.
- [java.lang.module package — Resolution and Readability](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html): phân giải module graph và thiết lập các cạnh đọc.
- [dev.java — Optional Dependencies with requires static](https://dev.java/learn/modules/optional-dependencies/): ví dụ và thực hành với dependency tùy chọn.
- [JDK 21 javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `--module-source-path`, `--module-path`, `--release` và biên dịch nhiều named modules.
- [JDK 21 java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--module-path`, `--add-modules` và `--show-module-resolution`.

**Một module được nhìn thấy trên module path chưa chắc đã được resolve; một module được resolve chưa chắc được mọi module khác đọc; một module được đọc chưa chắc export package cần dùng.** Ba ranh giới này giúp giải thích phần lớn lỗi JPMS khi biên dịch và triển khai các dependency bắc cầu hoặc tùy chọn.