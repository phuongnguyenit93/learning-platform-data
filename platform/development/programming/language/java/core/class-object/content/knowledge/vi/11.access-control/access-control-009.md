# Phân biệt quyền truy cập kiểu với khả năng nhìn thấy package trong module Java

Trong Java, câu hỏi **“Một lớp có `public` thì có dùng được từ nơi khác không?”** không thể luôn trả lời bằng việc chỉ nhìn modifier của lớp. Đối với một ứng dụng tổ chức thành **named modules** theo **Java Platform Module System (JPMS)**, cần kiểm tra cả **quyền truy cập kiểu** và **khả năng package chứa kiểu đó được module cung cấp ra bên ngoài**.

Ba điều kiện chính để mã trong **module A** dùng trực tiếp một kiểu của **module B** qua cú pháp Java thông thường là:

1. **A đọc được B** (*module readability*), thường nhờ `requires B;` trong `module-info.java`.
2. **B export package chứa kiểu cho A**, thường nhờ `exports package.name;` hoặc `exports package.name to A;`.
3. **Bản thân kiểu có quyền truy cập phù hợp**, ví dụ một top-level class cần `public` nếu được sử dụng từ một package khác; tiếp theo, constructor, field và method được gọi cũng phải có mức truy cập phù hợp.

Nếu thiếu một điều kiện, trình biên dịch có thể từ chối lời gọi, **dù mã nguồn của lớp được ghi `public`**.

Ví dụ ý tưởng:

```java
// Trong module library.core:
module library.core {
    exports library.api;
}
```

```java
// Trong package library.api:
package library.api;

public class Greeting {
    public String text() {
        return "Xin chào";
    }
}
```

```java
// Trong module app.main:
module app.main {
    requires library.core;
}
```

Mã ở module `app.main` có thể sử dụng `library.api.Greeting` vì package `library.api` được export, kiểu `Greeting` là `public` và module `app.main` đọc được `library.core`.

Nhưng nếu module `library.core` **không export** `library.api`, thì `public class Greeting` **không đủ** để cho phép module `app.main` import kiểu theo cách biên dịch thông thường.

Đó là sự khác biệt cốt lõi:

- **`public` trên kiểu** trả lời: *Trong những phạm vi mà kiểu có thể được truy cập, mã nào được sử dụng kiểu này?*
- **`exports` trên module** trả lời: *Package nào được công bố cho những module khác sử dụng trực tiếp các kiểu public?*
- **`requires` ở module tiêu thụ** trả lời: *Module này có đọc được module cung cấp API hay không?*

Bài này dùng Java 17+ với cấu trúc tệp, lệnh biên dịch/chạy, stdout và các tình huống dễ nhầm giữa `public`, package-private, `exports`, `opens` và reflection.

## 1. Bốn khái niệm cần tách riêng

| Khái niệm | Được khai báo tại | Trả lời câu hỏi |
| --- | --- | --- |
| **Quyền truy cập của kiểu** | `public class Foo`, `class Foo`, modifier của nested type | Ai được phép sử dụng tên kiểu `Foo`? |
| **Quyền truy cập thành viên** | `public Foo()`, `private int x`, `protected void m()`… | Ai được gọi constructor/field/method tương ứng? |
| **Module readability** | `requires other.module;` và các quy tắc module khác | Module sử dụng có thể “đọc” module chứa định nghĩa không? |
| **Export package** | `exports some.package;`, `exports some.package to another.module;` | Package nào được module cho phép dùng API public từ ngoài? |

Đối với việc gọi một constructor, còn phải xét **chữ ký phù hợp**, overload và khả năng truy cập chính constructor đó. Một package được export chỉ làm **API công khai của các kiểu truy cập được** trở nên khả dụng; nó không tự công khai mọi chi tiết bên trong.

### Các tầng kiểm tra

```text
Mã trong module app.client muốn dùng library.api.Greeting
                            |
                            v
          app.client đọc được library.core?
                 /                     \
               Không                    Có
                |                        |
        Không truy cập                 v
                            library.core export library.api
                            cho app.client?
                                 /          \
                               Không         Có
                                |             |
                        Không truy cập        v
                                   Greeting có public
                                   và kiểu truy cập được?
                                        /        \
                                      Không       Có
                                       |           |
                               Không truy cập      v
                                      Thành viên muốn gọi
                                      có truy cập được?
                                         /       \
                                       Không      Có
                                        |          |
                                Lỗi truy cập    Lời gọi có thể
                                                hợp lệ về access
```

Sơ đồ chỉ trình bày **điều kiện về khả năng truy cập**. Một chương trình vẫn có thể lỗi biên dịch vì sai kiểu đối số, constructor không tồn tại, import sai tên, classpath/module path không phù hợp, v.v.

## 2. Không có một “modifier `public`” cho package

Cú pháp:

```java
package library.api;
```

chỉ khai báo **tên package** mà đơn vị biên dịch Java thuộc về. Bản thân một Java package **không khai báo `public` hay `private`** giống field hoặc class.

Hai thao tác độc lập:

1. Trong tệp Java của kiểu, chọn modifier, chẳng hạn `public class Greeting` hay `class Helper`.
2. Trong `module-info.java` của named module, chọn package nào được **export**.

Ví dụ:

```java
module library.core {
    exports library.api;
}
```

Mệnh đề `exports library.api;` **không đổi modifier của những kiểu** trong package này. Nếu `library.api` có một `class HiddenHelper` package-private, kiểu đó vẫn là package-private mặc dù package đã được export.

**Không có cú pháp** `public package library.api;` để thay `exports`. `exports` là một **module directive**, không phải access modifier của class.

### Package không tự “export mọi package con”

`exports library.api;` áp dụng cho **đúng package `library.api`**.

Nó **không ngầm export**:

- `library.api.internal`;
- `library.api.dto`;
- `library.api.impl`.

Nếu muốn công bố thêm package, khai báo `exports` cho chính package tương ứng. Các tên package có chung tiền tố vẫn là **các package khác nhau**.

## 3. Hai kiểu truy cập của top-level class

Với **top-level class** thông thường, Java cho phép:

```java
public class PublicType {
}
```

hoặc:

```java
class PackageType {
}
```

- `PublicType` là public.
- `PackageType` là **package-private** do không có modifier truy cập.
- Top-level class **không được** khai báo `private class PackageType` hoặc `protected class PackageType`.
- Quy tắc `private`/`protected` dành cho những member type lồng bên trong và cho field/method/constructor có ngữ cảnh phù hợp, không phải top-level class.

Một class package-private không trở nên public khi module export package chứa nó.

```java
package library.api;

class Helper {
    static String value() {
        return "Nội bộ";
    }
}
```

Nếu module chứa class khai báo `exports library.api;`, mã ở package khác trong module tiêu thụ vẫn **không** được viết:

```java
import library.api.Helper;  // Lỗi: Helper không public
```

Không có mâu thuẫn nào: **package được export**, nhưng **kiểu Helper không có quyền public**.

## 4. Named module, `module-info.java` và `requires`

Một named module tường minh được khai báo trong `module-info.java`:

```java
module app.client {
    requires library.core;
}
```

Ở đây:

- `app.client` là tên module hiện tại.
- `library.core` là tên một module khác mà module hiện tại cần đọc.
- `requires library.core;` tạo quan hệ **readability** từ `app.client` đến `library.core`, khi module graph được giải quyết hợp lệ.
- `requires` **không** buộc `library.core` export tất cả package cho `app.client`.

Một named module có thể **đọc module B** nhưng vẫn không được trực tiếp truy cập các class public nằm trong package **không export** của B.

### `java.base` là trường hợp đặc biệt

Các named module thông thường ngầm có khả năng đọc `java.base`, cung cấp các API nền tảng như `java.lang` và `java.util`. Bạn thường **không phải viết**:

```java
requires java.base;
```

để dùng `String`, `Object` hoặc `ArrayList`.

`requires` được dùng cho các named modules khác mà module của bạn trực tiếp phụ thuộc, hoặc trong các tình huống đặc biệt theo JPMS.

### Đừng nhầm module name với package name

`module library.core` là tên **module**. `package library.api` là tên **package**. Hai tên không bắt buộc trùng nhau.

Một module có thể chứa nhiều package:

```text
library.core (module)
├── library.api
├── library.internal
└── library.data
```

Mỗi `exports` chọn một **package**, không phải tự động chọn cả module hay toàn bộ tên có chung tiền tố.

## 5. Ví dụ hoàn chỉnh: module export API, giấu package nội bộ

Đây là chương trình **Java 17 có thể biên dịch/chạy** minh họa ba tầng: module đọc được, package export, class public.

### 5.1. Cấu trúc thư mục

Từ một thư mục làm việc mới:

```text
src/
├── academy.lib/
│   ├── module-info.java
│   └── academy/
│       └── lib/
│           ├── api/
│           │   └── Greeting.java
│           └── internal/
│               └── SecretText.java
└── academy.app/
    ├── module-info.java
    └── academy/
        └── app/
            └── Main.java
```

### 5.2. Module cung cấp thư viện

**`src/academy.lib/module-info.java`**

```java
module academy.lib {
    exports academy.lib.api;
}
```

Chỉ package `academy.lib.api` được export. Package `academy.lib.internal` không được export ra ngoài.

**`src/academy.lib/academy/lib/internal/SecretText.java`**

```java
package academy.lib.internal;

public final class SecretText {
    private SecretText() {
    }

    public static String suffix() {
        return " từ thư viện";
    }
}
```

**Chú ý:** `SecretText` là **public class** và method `suffix()` là **public static**. Nó vẫn nằm trong **package không export**. Vì vậy public **không đủ** để cho phép module `academy.app` trực tiếp sử dụng nó.

**`src/academy.lib/academy/lib/api/Greeting.java`**

```java
package academy.lib.api;

import academy.lib.internal.SecretText;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào " + name + SecretText.suffix();
    }
}
```

`Greeting` là public class trong **package export**. Nó được phép import `SecretText` từ package internal vì hai lớp thuộc **cùng module `academy.lib`** và `SecretText` là public.

Không export `academy.lib.internal` **không ngăn code trong chính module `academy.lib` dùng các kiểu public của package đó**.

### 5.3. Module tiêu thụ

**`src/academy.app/module-info.java`**

```java
module academy.app {
    requires academy.lib;
}
```

**`src/academy.app/academy/app/Main.java`**

```java
package academy.app;

import academy.lib.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("An"));

        // academy.lib.internal.SecretText.suffix();
        // SAI nếu bỏ comment: package academy.lib.internal
        // không được academy.lib export cho academy.app.
    }
}
```

### 5.4. Biên dịch và chạy

Từ thư mục chứa `src`:

```bash
javac -encoding UTF-8 --module-source-path src -d mods -m academy.lib,academy.app
java --module-path mods -m academy.app/academy.app.Main
```

**Stdout chính xác:**

```text
Xin chào An từ thư viện
```

Giải thích kết quả:
1. `academy.app` **đọc được** `academy.lib` nhờ `requires academy.lib;`.
2. `academy.lib` **export `academy.lib.api`**, nên `academy.app` được nhìn thấy class public `Greeting`.
3. `Greeting.message` chạy mã nội bộ thư viện, gọi `SecretText.suffix` từ **package không export** nhưng nằm **trong cùng module**, nên hợp lệ.
4. `academy.app` không có quyền tự import/call `SecretText` dù kiểu này là public, vì package chứa nó không được export ra ngoài.
5. Lệnh `java --module-path mods -m academy.app/academy.app.Main` khởi chạy main class của named module `academy.app`.

Đây là ví dụ điển hình cho mục tiêu JPMS: **công bố API có chủ đích, che giấu implementation package**.

## 6. Nếu thiếu `requires` thì chuyện gì xảy ra?

Trong ví dụ trên, giả sử xóa dòng:

```java
requires academy.lib;
```

khỏi `academy.app/module-info.java` nhưng vẫn giữ:

```java
import academy.lib.api.Greeting;
```

thì module `academy.app` không thiết lập quan hệ đọc cần thiết tới `academy.lib` trong module graph thông thường. Việc `academy.lib.api` được export **không tự tạo quyền đọc** cho mọi module.

Một lỗi thường liên quan đến nội dung kiểu:

```text
package academy.lib.api is not visible
(module academy.app does not read module academy.lib)
```

Thông báo `javac` cụ thể có thể thay đổi theo lệnh biên dịch/cách modules được giải quyết, nhưng bản chất là **thiếu module readability**.

**Cách sửa:** giữ `requires academy.lib;` trong module tiêu thụ, bảo đảm module `academy.lib` xuất hiện hợp lệ trên module path và được resolve.

Không sửa bằng cách biến `Greeting` thành `public` lần nữa: class đã public, vướng mắc nằm ở **module readability**.

## 7. Nếu có `requires` nhưng package không được `exports`?

Giữ:

```java
module academy.app {
    requires academy.lib;
}
```

nhưng sửa module thư viện thành:

```java
module academy.lib {
    // Không exports academy.lib.api;
}
```

Khi đó `academy.app` **đọc được** `academy.lib` nhưng **không được phép dùng trực tiếp package `academy.lib.api`** từ bên ngoài.

Một lỗi điển hình:

```text
package academy.lib.api is not visible
(package academy.lib.api is declared in module academy.lib,
 which does not export it)
```

**Cách sửa đúng phụ thuộc hợp đồng API:**

- Nếu `academy.lib.api` thực sự là API công khai: khai báo `exports academy.lib.api;`.
- Nếu package cố ý nội bộ: không export; thay vào đó cung cấp một public facade/interface trong package được export.
- Nếu muốn mở **chỉ cho một vài module cụ thể**, cân nhắc **qualified exports** (`exports ... to ...`).

**Không nên** đổi toàn bộ internal packages thành export chỉ để một phép import lẻ biên dịch được; như vậy sẽ làm phình bề mặt API của thư viện.

## 8. Một package được export không có nghĩa mọi kiểu đều public

Ngay trong package `academy.lib.api`, ta có thể khai báo:

**`PublicEndpoint.java`**

```java
package academy.lib.api;

public class PublicEndpoint {
    public String name() {
        return InternalFormatter.format("An");
    }
}
```

**`InternalFormatter.java`**

```java
package academy.lib.api;

final class InternalFormatter {
    private InternalFormatter() {
    }

    static String format(String input) {
        return "[" + input + "]";
    }
}
```

Giả sử module chứa hai tệp đã `exports academy.lib.api;`:

- Class `PublicEndpoint` public nên caller bên ngoài module có thể truy cập **nếu module readable**.
- Class `InternalFormatter` **package-private**, nên **không** trở thành loại public API vì package đã export.
- `PublicEndpoint` được phép gọi `InternalFormatter.format` do hai lớp trong **cùng package** và đúng ngữ cảnh.
- Mã trong package khác không import `academy.lib.api.InternalFormatter` trực tiếp.

Nguyên tắc chính xác là: `exports` **làm cho public types và những thành viên có thể truy cập hợp lệ của chúng** được sử dụng từ các module được cấp phép. Nó **không** làm package-private types/members thành public.

### Package-private khác “nội bộ module”

Package-private nghĩa là phạm vi **package**, không phải toàn module.

Nếu có:

```java
package academy.lib.api;

class Helper {
}
```

thì một lớp thuộc **`academy.lib.internal`**, dù nằm **cùng module**, cũng không thể dùng `Helper` trực tiếp như một top-level public class. Cùng module giúp giải quyết **exports**, nhưng **không vô hiệu hóa Java access modifiers**.

Tóm tắt hai chiều:

- **Public class trong unexported package:** code khác package **cùng module** có thể dùng nếu thỏa access rules, nhưng module ngoài không được dùng trực tiếp.
- **Package-private class trong exported package:** code **cùng package** có thể dùng, nhưng module khác không được dùng chỉ vì package đã export.

## 9. Quyền truy cập thành viên là tầng kiểm tra tiếp theo

Ngay cả khi module `academy.app` đọc được `academy.lib`, package đã export, class đã public, vẫn cần xem **constructor, field và method** được gọi.

Giả sử:

```java
package academy.lib.api;

public class Customer {
    private final String id;
    int points;
    protected String group;

    private Customer(String id) {
        this.id = id;
        this.group = "DEFAULT";
    }

    public static Customer of(String id) {
        return new Customer(id);
    }

    public String id() {
        return id;
    }
}
```

Từ một class độc lập khác package thuộc module đọc được API:

```java
Customer customer = Customer.of("C-1");
System.out.println(customer.id()); // C-1

// new Customer("C-1");     // SAI: constructor private
// System.out.println(customer.points); // SAI: package-private
// System.out.println(customer.group);  // SAI nếu caller không có
//                                        // ngữ cảnh protected hợp lệ
```

Điều kiện module đã được đáp ứng, nhưng từng thành viên vẫn chịu **Java access control**:

- `private` constructor vẫn private.
- Package-private field vẫn chỉ mở cho mã trong package tương ứng.
- `protected` vẫn có quy tắc cùng package và subclass đặc biệt.
- `public` method là API công khai nếu các tầng truy cập bên ngoài đều hợp lệ.

**Không có mệnh đề `exports` nào biến `private Customer(...)` thành constructor public.**

## 10. `protected` vẫn có quy tắc riêng qua module

`exports` không thay thế luật truy cập của `protected`.

Giả sử một thư viện export package `core.api`:

```java
package core.api;

public class Base {
    protected int value = 1;

    protected Base() {
    }

    protected void increase() {
        value++;
    }

    public int getValue() {
        return value;
    }
}
```

Một lớp con thuộc module/package khác mà **đọc được module thư viện** có thể:

```java
class Derived extends Base {
    Derived() {
        super();         // protected superclass constructor hợp lệ
    }

    void update() {
        this.increase(); // protected instance method trên this hợp lệ
    }
}
```

Tuy nhiên, nếu ở ngoài package khai báo, **một mã không phải subclass** không được gọi `new Base()` chỉ vì module export package, và không được dùng `otherBase.value`.

Ngay trong subclass ngoài package, phép truy cập protected **instance member** bằng receiver cũng có ràng buộc kiểu; không được mặc nhiên dùng `Base other; other.value` như khi ở cùng package.

### Access theo package và module không thay thế nhau

Một cách dễ nhớ:

- `exports` giải quyết **cổng module** đối với package.
- `protected` giải quyết **quyền thành viên** dựa trên package/kế thừa.
- `super(...)` giải quyết **gọi constructor lớp cha hợp lệ**.
- Điều kiện của cả ba cùng phải được đáp ứng.

## 11. `exports` vô điều kiện và qualified exports

JPMS hỗ trợ hai hình thức:

```java
exports catalog.api;
```

và:

```java
exports catalog.spi to catalog.plugin;
```

### `exports catalog.api;`

Đây là **unqualified export**: package `catalog.api` được export cho **các module đọc được module cung cấp** nói chung, không giới hạn danh sách tên module nhận export.

### `exports catalog.spi to catalog.plugin;`

Đây là **qualified export**: package `catalog.spi` chỉ được export cho module được liệt kê, ở đây là `catalog.plugin`.

Một module khác như `catalog.app` **không** được dùng trực tiếp `catalog.spi` chỉ vì nó `requires catalog.core;`.

Cần lưu ý:

- Qualified export vẫn yêu cầu kiểu được dùng có access modifier phù hợp.
- Module nhận export cũng cần **readability** đến module chứa package.
- Qualified export **không đồng nghĩa `opens`** cho deep reflection.
- Danh sách `to` có thể chứa nhiều tên module được phép.

## 12. Chương trình hoàn chỉnh: qualified export cho module đối tác

Ví dụ gồm **ba named modules** tách biệt với ví dụ trước.

### 12.1. Cấu trúc tệp

```text
src/
├── catalog.core/
│   ├── module-info.java
│   └── catalog/
│       ├── api/
│       │   └── Product.java
│       └── spi/
│           └── InternalPrice.java
├── catalog.plugin/
│   ├── module-info.java
│   └── catalog/
│       └── plugin/
│           └── PriceFormatter.java
└── catalog.app/
    ├── module-info.java
    └── catalog/
        └── app/
            └── Main.java
```

**`src/catalog.core/module-info.java`**

```java
module catalog.core {
    exports catalog.api;
    exports catalog.spi to catalog.plugin;
}
```

**`src/catalog.core/catalog/api/Product.java`**

```java
package catalog.api;

public final class Product {
    private final int price;

    public Product(int price) {
        this.price = price;
    }

    public int price() {
        return price;
    }
}
```

**`src/catalog.core/catalog/spi/InternalPrice.java`**

```java
package catalog.spi;

public final class InternalPrice {
    private InternalPrice() {
    }

    public static String format(int value) {
        return value + " VND";
    }
}
```

**`src/catalog.plugin/module-info.java`**

```java
module catalog.plugin {
    requires catalog.core;
    exports catalog.plugin;
}
```

**`src/catalog.plugin/catalog/plugin/PriceFormatter.java`**

```java
package catalog.plugin;

import catalog.api.Product;
import catalog.spi.InternalPrice;

public final class PriceFormatter {
    private PriceFormatter() {
    }

    public static String label(Product product) {
        return "Giá: " + InternalPrice.format(product.price());
    }
}
```

`catalog.plugin` có thể import `catalog.spi.InternalPrice` vì module cung cấp chỉ định **`exports catalog.spi to catalog.plugin;`**, và plugin khai báo `requires catalog.core;`.

**`src/catalog.app/module-info.java`**

```java
module catalog.app {
    requires catalog.core;
    requires catalog.plugin;
}
```

**`src/catalog.app/catalog/app/Main.java`**

```java
package catalog.app;

import catalog.api.Product;
import catalog.plugin.PriceFormatter;

public class Main {
    public static void main(String[] args) {
        Product book = new Product(120);
        System.out.println(PriceFormatter.label(book));

        // catalog.spi.InternalPrice.format(120);
        // SAI nếu bỏ comment: catalog.app không được
        // catalog.core export package catalog.spi.
    }
}
```

### 12.2. Biên dịch/chạy

```bash
javac -encoding UTF-8 --module-source-path src -d mods -m catalog.core,catalog.plugin,catalog.app
java --module-path mods -m catalog.app/catalog.app.Main
```

**Stdout:**

```text
Giá: 120 VND
```

Phân tích:
1. `catalog.core` export `catalog.api` cho các module đọc được nó, nên `catalog.app` dùng được `Product`.
2. `catalog.core` chỉ export `catalog.spi` cho `catalog.plugin`.
3. `catalog.plugin` dùng được `InternalPrice` để xử lý phần implementation được ủy quyền.
4. `catalog.app` chỉ dùng API `Product` và `PriceFormatter`, không được tự import `InternalPrice`.
5. `PriceFormatter.label(Product)` là public API của module plugin, còn cách plugin gọi internal SPI là chi tiết ẩn khỏi module app.

**Lợi ích:** thư viện có thể hợp tác với một module đối tác cụ thể mà không công khai toàn bộ SPI cho mọi module.

## 13. `opens` khác `exports`: compile-time API và deep reflection

Một điểm rất dễ nhầm trong Java 9+ là hai chỉ thị:

```java
exports demo.api;
opens demo.internal;
```

Chúng không đồng nghĩa.

| Tiêu chí | `exports demo.api;` | `opens demo.internal;` |
| --- | --- | --- |
| Cho module khác trực tiếp import public type theo source code? | **Có**, nếu module đọc được và type public | **Không**, chỉ vì `opens` |
| Truy cập public members qua reflection | Có, theo điều kiện module/access phù hợp | Có |
| Cho phép *deep reflection* như thử `setAccessible(true)` vào private member? | **Không** chỉ vì export | **Có** trong phạm vi module/package được mở và điều kiện runtime |
| Áp dụng ở giai đoạn chủ yếu | Kiểm tra access tại compile time và runtime | Reflection tại runtime |
| Có hình thức giới hạn module cụ thể? | `exports p to m;` | `opens p to m;` |

### Quan trọng về cách diễn đạt

`opens` không tạo một “public import” từ package bị ẩn. Nó **mở package cho cơ chế reflection** trong phạm vi được phép. Một module khác có thể sử dụng `Class.forName(...)` hoặc một framework dựa trên reflection, nhưng source code **không thể chỉ `import` kiểu trong package không export** vì đã `opens` nó.

Trong nhiều ứng dụng framework (dependency injection, ORM, serialization), một package chứa các đối tượng cần truy cập bằng reflection có thể được **opens** cho framework, trong khi **không exports** thành API biên dịch công khai.

### Qualified opens

```java
opens demo.entity to orm.framework;
```

cho phép reflection theo quyền opens của package `demo.entity` cho module `orm.framework`, **không mở cho mọi module**.

Đây là một cách giảm quyền so với `opens demo.entity;` không giới hạn.

## 14. Ví dụ runnable: `opens` cho reflection nhưng không export implementation

Ví dụ có hai modules độc lập với những ví dụ trước.

### 14.1. Thư mục

```text
src/
├── vault.core/
│   ├── module-info.java
│   └── vault/
│       ├── api/
│       │   └── Factory.java
│       └── impl/
│           └── SecretBean.java
└── inspector.app/
    ├── module-info.java
    └── inspector/
        └── app/
            └── Main.java
```

**`src/vault.core/module-info.java`**

```java
module vault.core {
    exports vault.api;
    opens vault.impl to inspector.app;
}
```

**`src/vault.core/vault/impl/SecretBean.java`**

```java
package vault.impl;

public final class SecretBean {
    private final String secret;

    public SecretBean(String secret) {
        this.secret = secret;
    }
}
```

**`src/vault.core/vault/api/Factory.java`**

```java
package vault.api;

import vault.impl.SecretBean;

public final class Factory {
    private Factory() {
    }

    public static Object sample() {
        return new SecretBean("HIDDEN");
    }
}
```

**`src/inspector.app/module-info.java`**

```java
module inspector.app {
    requires vault.core;
}
```

**`src/inspector.app/inspector/app/Main.java`**

```java
package inspector.app;

import java.lang.reflect.Field;
import vault.api.Factory;

public class Main {
    public static void main(String[] args) throws Exception {
        Object bean = Factory.sample();
        Field field = bean.getClass().getDeclaredField("secret");
        field.setAccessible(true);
        System.out.println(field.get(bean));

        // import vault.impl.SecretBean; // SAI về access:
        // vault.impl không được export.
    }
}
```

Trong source `Main.java`, dòng bình luận `import ...` chỉ là **minh họa**; nếu muốn thử import thật, import phải được đặt ở phần khai báo đầu tệp, không đặt trong method.

### 14.2. Biên dịch/chạy

```bash
javac -encoding UTF-8 --module-source-path src -d mods -m vault.core,inspector.app
java --module-path mods -m inspector.app/inspector.app.Main
```

**Stdout:**

```text
HIDDEN
```

Tại sao chạy được?
1. Module `inspector.app` có `requires vault.core;` và package `vault.api` được export, vì vậy caller dùng được `Factory`.
2. `Factory.sample()` trả về một đối tượng thực tế của class `vault.impl.SecretBean` nhưng **kiểu trả về công khai là `Object`**.
3. `vault.impl` **không được export**. Vì thế `Main` không thể trực tiếp import `SecretBean` theo API compile-time thông thường.
4. `getDeclaredField("secret")` dùng reflection lấy thông tin field private.
5. `field.setAccessible(true)` được phép trong trường hợp này vì `vault.core` đã khai báo **`opens vault.impl to inspector.app;`**.
6. `field.get(bean)` đọc giá trị field private và in `HIDDEN`.

Nếu bỏ directive `opens vault.impl to inspector.app;`, `setAccessible(true)` trong ví dụ sẽ không còn được phép vượt qua access checks đối với private field này, và có thể ném `java.lang.reflect.InaccessibleObjectException` theo quy tắc JPMS/JDK 17.

**Giới hạn cần biết:** reflection với `setAccessible` không nên được dùng để vượt API tùy tiện. `opens` cấp một quyền truy cập rộng đáng kể cho module nhận quyền; hãy giữ phạm vi package/module cần thiết và cân nhắc framework đáng tin cậy.

## 15. `open module` là gì?

Ngoài `opens package.name;`, JPMS có dạng:

```java
open module application.entities {
    requires java.sql;
}
```

Một **open module** về nguyên tắc mở các package chứa trong module cho **deep reflection** ở runtime theo quy tắc JPMS.

Điều này **không tương đương** với export mọi package cho những import source code. Nếu không khai báo `exports` phù hợp, mã module khác vẫn không tự được quyền biên dịch sử dụng các kiểu public trong những package đó qua import thông thường.

**Lưu ý cú pháp:** trong khai báo `open module`, không dùng `opens` directive riêng cho từng package như trong module thông thường; bản thân open module đã là khai báo mức module.

### Nên dùng dạng nào?

- `opens p to framework.module;`: lựa chọn hẹp, thích hợp khi chỉ framework cụ thể cần phản chiếu một package.
- `opens p;`: mọi module có thể thực hiện deep reflection theo ngữ nghĩa được mở đối với package đó.
- `open module ...`: rộng hơn; chỉ dùng khi mô hình ứng dụng cần mở nhiều package và bạn hiểu hệ quả.

Không nên chọn `open module` chỉ vì “dễ biên dịch”: nó **không sửa điều kiện exports**, mà còn mở rộng khả năng reflection.

## 16. `requires transitive` và khả năng đọc xuyên qua dependency

Đôi khi module API của bạn công bố các kiểu thuộc một module khác như phần hợp đồng công khai.

Ví dụ ý tưởng:

```java
module types.model {
    exports types.api;
}
```

```java
module facade.api {
    requires transitive types.model;
    exports facade.api;
}
```

```java
module consumer.app {
    requires facade.api;
}
```

`requires transitive types.model;` nghĩa là các module đọc `facade.api` theo quan hệ tương ứng có thể được cấp khả năng **đọc `types.model` theo tính bắc cầu**.

Nếu `facade.api` chứa:

```java
package facade.api;

public class Service {
    public types.api.Model getModel() {
        return new types.api.Model();
    }
}
```

thì kiểu `types.api.Model` xuất hiện trong public signature. Muốn caller của `facade.api` có thể dùng API ấy thuận lợi, `requires transitive types.model;` có thể phù hợp, **nhưng `types.model` vẫn phải export `types.api`** để code được phép truy cập class public trong package đó.

**Không được hiểu `requires transitive` là export lại mọi package**. Nó ảnh hưởng đến **readability**, còn **exports** vẫn là quyết định độc lập của module sở hữu package.

Đoạn minh họa trên giả định `types.api.Model` là class public có constructor phù hợp; nó giải thích dependency chứ không phải dự án đầy đủ với cấu trúc tệp.

### `requires static` để làm gì?

`requires static optional.module;` biểu thị phụ thuộc cần thiết ở compile time nhưng không bắt buộc phải có theo cùng cách tại runtime trong các tình huống liên quan. Nó hữu ích với những dependency tùy chọn, annotation hoặc API có thể không được sử dụng ở runtime.

`requires static` **không mở public types** của một unexported package. Đừng dùng nó để giải quyết lỗi visibility do thiếu `exports`.

## 17. Vì sao cùng module vẫn có thể truy cập public type ở package không export?

Điểm này giúp hiểu đúng `exports`.

Giả sử module có cấu trúc:

```text
service.engine
  ├── service.api
  ├── service.internal
  └── service.logic
```

và:

```java
module service.engine {
    exports service.api;
}
```

Các class `public` trong `service.logic` vẫn có thể import class `public` trong `service.internal`, vì cả hai ở **cùng module** và đáp ứng quyền truy cập type.

`exports` là ranh giới **giữa các module**, không phải quy tắc “mọi package trong module bị cấm nhìn lẫn nhau”.

Tuy nhiên:
- Một **package-private class** trong `service.internal` vẫn không được mã `service.logic` dùng trực tiếp chỉ vì chúng cùng module.
- Một **private member** vẫn là private theo quy tắc Java.
- Một kiểu public trong `service.internal` vẫn bị **che khỏi module ngoài** nếu package không export.

**Kết luận ngắn:** *Sama module* không tự mở access modifier của type/member; *exported package* không tự mở access modifier của type/member. Hai trục độc lập.

## 18. Package-private, cùng tên package và ranh giới module

Khi chưa có JPMS, nhiều ví dụ Java giải thích package-private bằng câu “class khác cùng package được truy cập”. Trong ứng dụng named modules, còn cần quan tâm rằng **package gắn với ngữ cảnh module**.

Đừng giả định rằng đặt cùng khai báo:

```java
package shared.api;
```

trong hai named modules khác nhau là cách hợp pháp để “lách” package-private. **Split packages** giữa các named modules cùng tham gia module graph có thể dẫn đến lỗi biên dịch/giải quyết module và không phải mô hình hợp tác package-private được JPMS thiết kế hỗ trợ.

Nếu hai phần mềm thuộc hai module khác nhau cần tương tác, hãy công bố một **public API** trong exported package phù hợp, hoặc dùng interface/facade/service abstraction.

### Package không phải module

Ví dụ:
- Module `finance.core` có package `finance.api`, `finance.internal`.
- Module `finance.app` có package `finance.app`.

Không có điều kiện rằng **tên package phải bắt đầu bằng tên module** để JPMS hoạt động, dù quy ước tổ chức như vậy thường giúp dễ đọc.

Lời khuyên quan trọng hơn là tránh đặt các package trùng tên vào nhiều named modules một cách làm phát sinh split package conflict.

## 19. Classpath và module path: vì sao chương trình cũ có thể không có lỗi `exports`?

Java 17 vẫn chạy được ứng dụng theo mô hình **classpath truyền thống**.

Nếu dùng classpath mà không tổ chức ứng dụng thành những explicit named modules, nhiều kiểm tra ứng dụng được nhìn theo **unnamed module**. Trong một dự án Java đơn giản:

```text
src/
├── library/
│   └── Greeting.java
└── app/
    └── Main.java
```

**`src/library/Greeting.java`**

```java
package library;

public class Greeting {
    public static String text() {
        return "Hello";
    }
}
```

**`src/app/Main.java`**

```java
package app;

import library.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.text());
    }
}
```

Biên dịch và chạy kiểu classpath:

```bash
javac -encoding UTF-8 -d out src/library/Greeting.java src/app/Main.java
java -cp out app.Main
```

Stdout:

```text
Hello
```

Ở ví dụ này **không có `module-info.java`**, và không phải khai báo `exports library;` để `app.Main` dùng `library.Greeting`. Java vẫn kiểm tra `public`, package-private, private, protected theo quy tắc thông thường, nhưng không có explicit module `library.module` giới hạn `library` qua `exports`.

### Khi kết hợp classpath với named modules

Nếu ứng dụng classpath sử dụng thư viện named module trên module path, việc **module được resolve** và **exports** của thư viện vẫn quan trọng. Có thể cần cấu hình `--add-modules` hoặc những chỉ thị phù hợp với topology.

**Không được kết luận “classpath luôn bỏ qua mọi module boundary”.** Đó là một quy tắc quá rộng và dễ sai khi kết hợp unnamed/named/automatic modules.

## 20. Automatic module khác explicit named module

Một JAR thường không có `module-info.class`, khi đặt trên **module path** có thể trở thành **automatic module** theo quy tắc JPMS.

Đặc điểm đáng chú ý:
- Nó có **tên module** được suy ra hoặc được cung cấp theo metadata như `Automatic-Module-Name`.
- Nó có đặc tính readability/export mở rộng theo quy tắc automatic module nhằm hỗ trợ chuyển tiếp từ classpath.
- Nó **không tương đương** với một explicit module có `module-info.java` mà bạn đã tự liệt kê `exports`.

Điều này giải thích vì sao một thư viện JAR trên module path có thể cho truy cập nhiều package hơn dự kiến nếu nó đang là **automatic module** thay vì **explicit named module**.

**Khi cần API đóng gói chặt**, nên kiểm tra thư viện đang được nạp dưới hình thức nào, thay vì chỉ nhìn tên JAR và cho rằng JPMS đang ngăn mọi truy cập internal packages.

### `Automatic-Module-Name` không phải `exports`

Manifest attribute `Automatic-Module-Name` giúp cung cấp tên module ổn định cho automatic module, nhưng **không tự biến nó thành explicit module với các exports có chọn lọc**. Một thư viện muốn kiểm soát chính xác exported packages cần module descriptor phù hợp.

## 21. `--add-exports` và `--add-opens`: ngoại lệ cấu hình, không phải thiết kế API mặc định

Một số hệ thống chuyển đổi từ Java cũ hoặc dùng framework có thể cần cấu hình runtime/compile-time để vượt hạn chế module.

Các tùy chọn phổ biến:

```bash
--add-exports module.name/package.name=target.module
```

```bash
--add-opens module.name/package.name=target.module
```

Ý nghĩa khái quát:
- **`--add-exports`**: điều chỉnh khả năng dùng public types trong một package vốn không export cho target được nêu, theo ngữ cảnh công cụ phù hợp.
- **`--add-opens`**: điều chỉnh khả năng reflective access vào package ở runtime cho target được nêu, theo các quy tắc có hiệu lực.

Hai tùy chọn **không tương đương**, và cú pháp chính xác có thể thay đổi theo bạn đang cấu hình `javac` hay `java`, có module tiêu thụ nào, cũng như mục tiêu `ALL-UNNAMED`.

**Lưu ý thực hành:**
1. Không dùng các tùy chọn này như cách giải quyết mặc định cho API thư viện do bạn kiểm soát.
2. Chỉ mở hoặc export **package thực sự cần** cho những module phù hợp.
3. `--add-opens` cho reflection **không sửa source-level import** của một public type trong unexported package.
4. `--add-exports` đối với public API **không tự cho phép truy cập private field** thông qua `setAccessible(true)` nếu package chưa được opened.

Nếu thấy cần nhiều `--add-exports` để truy cập các internal JDK packages như `jdk.internal.*`, đó là dấu hiệu cần xem lại việc phụ thuộc vào implementation detail không ổn định.

## 22. Quyền truy cập kiểu lồng nhau trong exported package

Một public top-level class nằm trong exported package có thể chứa nhiều kiểu lồng nhau với access modifiers khác nhau:

```java
package academy.lib.api;

public class Container {
    public static class PublicNested {
    }

    protected static class ProtectedNested {
    }

    static class PackageNested {
    }

    private static class PrivateNested {
    }
}
```

Nếu module đã export `academy.lib.api` cho caller, thì:
- `Container` là public top-level type.
- `Container.PublicNested` là **public nested type**, có thể được sử dụng từ nơi đủ điều kiện.
- `ProtectedNested` vẫn chịu luật protected.
- `PackageNested` vẫn là package-private.
- `PrivateNested` vẫn là private.

**Không phải chỉ vì package và outer class public thì mọi nested type tự public.** Các mức truy cập của nested types tiếp tục tham gia kiểm tra.

### Ví dụ dấu chấm trong tên kiểu

`Container.PublicNested` là một **member type**, không phải package `Container`. Hãy đọc đúng cấu trúc tên:
- `academy.lib.api` là package;
- `Container` là top-level class;
- `PublicNested` là nested class.

`exports academy.lib.api;` chọn package, không phải từng nested type. Quyền truy cập nested type do khai báo Java quyết định.

## 23. Exports không làm public class có thể khởi tạo nếu constructor private

Một trường hợp đơn giản:

```java
package academy.lib.api;

public final class Settings {
    private Settings() {
    }

    public static Settings create() {
        return new Settings();
    }
}
```

Giả sử module thư viện đã export `academy.lib.api`, module client có `requires academy.lib;`.

Caller **có thể**:

```java
Settings settings = Settings.create();
```

nhưng **không thể**:

```java
Settings settings = new Settings();
```

vì constructor `Settings()` là private. Không có mệnh đề `exports` nào xóa bỏ giới hạn access modifier của constructor này.

Điều này thường được sử dụng cho:
- Static factory methods;
- Utility classes;
- Controlled object lifecycle;
- Encapsulation hoặc API chỉ expose những cách tạo object nhất định.

`exports` giải quyết **module/package accessibility**; constructor vẫn được kiểm tra riêng.

## 24. `exports` có ảnh hưởng đến việc gọi public method trong unexported package không?

Giả sử:

```java
package academy.lib.internal;

public class InternalTool {
    public static String run() {
        return "OK";
    }
}
```

Mặc dù class và method đều `public`, module client không được trực tiếp `import academy.lib.internal.InternalTool;` nếu `academy.lib.internal` không export cho client.

**Public method bên trong public class ở unexported package không tự trở thành API direct-call từ ngoài module.**

Tuy nhiên, code ở **trong cùng module** có thể sử dụng class này như trong ví dụ `academy.lib.api.Greeting` gọi `SecretText`. Nếu một public facade method trong exported package **gọi giúp** InternalTool rồi trả một `String`, caller có thể dùng **facade** theo hợp đồng của API.

Đó là cách tách:
- **Bề mặt API được công bố** (exported packages).
- **Chi tiết implementation có thể dùng trong nội bộ module** (unexported packages).

Cách tách này thường giúp thay implementation mà không buộc module client thay import hoặc tham chiếu đến lớp nội bộ.

## 25. Ngữ cảnh reflection và public members của exported package

`exports` có ảnh hưởng tới reflection, nhưng cần phân biệt **public reflection** và **deep reflection**.

Với package đã export không điều kiện, module client có thể dùng reflection trên các **public members của public types** phù hợp, ví dụ:

```java
Class<?> type = Class.forName("academy.lib.api.Greeting");
System.out.println(type.getName());
```

Nhưng nếu muốn truy cập một **private field** bằng:

```java
Field field = type.getDeclaredField("secret");
field.setAccessible(true);
```

thì **`exports` một mình không mặc nhiên cho phép vượt private access** của named module. Cần xem module có **opens** package tới module caller hay không.

Không được suy luận rằng gọi `Class.forName` thành công đồng nghĩa được gọi mọi constructor, đọc mọi private field hay bypass module encapsulation. Class loading, visibility, member accessibility và reflective suppression of access checks là các lớp vấn đề khác nhau.

## 26. Một vài ngoại lệ: JNI, reflection và runtime enforcement

Các quy tắc access trong Java phần lớn được compiler áp dụng khi biên dịch mã nguồn, nhưng JVM/module system còn thực thi những ràng buộc runtime phù hợp khi liên kết/truy cập kiểu và thành viên.

Vì vậy tránh hai khẳng định quá mức:

- **“Mọi thứ chỉ kiểm tra lúc biên dịch.”** Không đúng trong mọi tình huống khi chạy bytecode, liên kết và reflection.
- **“`public` có nghĩa ai có class file cũng được dùng mọi thứ.”** Không đúng khi tính module exports/opens và quyền thành viên.

Một mô hình chính xác hơn:
- **Mã Java thông thường:** compiler phân tích kiểu, module readability, exports, access modifiers; JVM vẫn bảo vệ các giới hạn liên quan.
- **Reflection:** khả năng truy cập không hoàn toàn giống cú pháp import/gọi tĩnh; `exports` và `opens` đóng những vai trò khác nhau.
- **Cơ chế đặc biệt/đặc quyền:** có những API và cấu hình có thể điều chỉnh access, nhưng không phải lý do để bỏ qua thiết kế API.

Bài học này tập trung vào **mô hình có chủ đích cho Java 17**, không xem private, unexported package hoặc opens như một cơ chế an toàn tuyệt đối chống mã độc chạy với quyền cao.

## 27. Các lỗi phổ biến khi tổ chức dự án theo JPMS

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Class là `public` nhưng import từ module khác không được | Package chứa class không export cho client | Export đúng API package hoặc cung cấp facade |
| Package đã `exports` nhưng một class vẫn không import được | Class đó là package-private | Đưa class vào API public nếu thật sự cần, hoặc giữ nội bộ |
| `requires library.core;` mà vẫn báo package không visible | Library không exports đúng package/qualified export chưa cấp cho client | Kiểm tra `module-info.java` của library |
| Package export nhưng compiler báo module does not read | Thiếu readability ở module tiêu thụ | Thêm `requires` hoặc điều chỉnh module graph đúng |
| `exports p;` nhưng `p.internal` không truy cập được | Export không bao gồm subpackages | Export riêng nếu thật sự là API |
| `exports p to friend;` nhưng app khác không import được | Qualified export chỉ cấp cho module friend | Không lách bằng import; thiết kế API công khai hoặc điều chỉnh danh sách `to` |
| `opens p;` nhưng `import p.Type` vẫn lỗi | Opens không phải exports cho source-level API | Dùng exports nếu thật sự muốn public API |
| `exports p;` nhưng `setAccessible(true)` lên private field thất bại | Export không cấp deep reflection | Dùng qualified opens nếu framework thật sự cần |
| Public class trong exported package có constructor private | Constructor không truy cập được | Dùng factory/public constructor phù hợp |
| Public method trong class package-private không gọi trực tiếp được | Kiểu chứa không public | Tạo public facade/type trong exported package |
| Package-private method khác package không gọi được dù cùng module | Cùng module không xóa access modifier | Dùng public/protected API phù hợp |
| Dùng `--add-exports` để mở private field | Add-exports không đồng nghĩa opens | Phân biệt public source access và deep reflection |
| Classpath project chạy được, chuyển module path thì lỗi | Named module thêm requires/exports và package conflict | Thiết kế module descriptor, sửa module graph |
| Hai named modules chứa cùng package gây lỗi | Split packages | Tổ chức lại ranh giới package/module |
| `requires transitive` nhưng API type của dependency vẫn không dùng được | Dependency package không exports | Module sở hữu type phải export API package |
| Public type trong module không export được API đúng cách | Package name sai, module name sai, source path sai | Kiểm tra đường dẫn package và module source layout |
| Framework dùng reflection thất bại trên Java 17 | Package chứa entity/model không được opens cho framework | Cấp quyền opens hẹp theo contract framework |
| Đặt module chỉ vì tên package giống tên module | Nhầm giữa namespace package và module | Kiểm tra từng `module-info.java` và package thực |

## 28. Bài tự luyện có đáp án

### Bài 1 — Class public, package chưa export

Thư viện:

```java
module demo.lib {
}
```

```java
package demo.api;

public class Hello {
    public static String text() {
        return "Hi";
    }
}
```

Module app có:

```java
module demo.app {
    requires demo.lib;
}
```

App có được viết `import demo.api.Hello;` không?

**Đáp án:** **Không**, vì `demo.lib` chưa export `demo.api`. `public class Hello` chỉ giải quyết quyền của kiểu, không mở package qua module boundary. Cách sửa nếu muốn công bố API: thêm `exports demo.api;` vào `demo.lib/module-info.java`.

### Bài 2 — Package export, kiểu package-private

```java
module demo.lib {
    exports demo.api;
}
```

```java
package demo.api;

class Hidden {
}
```

Module app đã `requires demo.lib;`. Có import được `demo.api.Hidden` không?

**Đáp án:** **Không**. Package đã export, nhưng top-level class `Hidden` **không public**. Đổi exports không thay modifier. Nếu cần public API, người thiết kế thư viện phải công bố một kiểu public phù hợp.

### Bài 3 — Đủ điều kiện dùng public API chưa?

```java
module lib.one {
    exports lib.api;
}
```

```java
module app.one {
    requires lib.one;
}
```

```java
package lib.api;

public class Item {
    public Item() {
    }

    public String id() {
        return "A";
    }
}
```

Một lớp `app.client.Main` thuộc module `app.one` có thể `new Item()` sau import không?

**Đáp án:** **Có**, nếu module được biên dịch/resolve đúng. App đọc `lib.one`, package `lib.api` được export, class `Item` là public, constructor no-arg là public.

### Bài 4 — Thiếu `requires` nhưng có `exports`

Module `lib.one` export `lib.api`. Module `app.one` không có `requires lib.one;` nhưng source import `lib.api.Item`.

**Đáp án:** Trong mô hình named modules thông thường, **không được** vì module client chưa có readability phù hợp đến `lib.one`. `exports` không tự thay `requires`.

### Bài 5 — Qualified export

```java
module company.core {
    exports company.spi to company.plugin;
}
```

Cả `company.plugin` và `company.app` đều `requires company.core;`. Module nào được dùng trực tiếp kiểu public trong `company.spi`?

**Đáp án:** `company.plugin` được cấp export; `company.app` **không**. Điều kiện public class/member vẫn phải được kiểm tra tiếp ở module plugin.

### Bài 6 — `opens` có thay thế `exports` không?

```java
module entities {
    opens example.entity to orm.tool;
}
```

Với `public class User` thuộc package `example.entity`, `orm.tool` đã có quan hệ đọc cần thiết. Module orm có thể đơn giản `import example.entity.User;` chỉ vì `opens` không?

**Đáp án:** **Không**. `opens` phục vụ reflective access tại runtime, không cấp quyền import public type theo compile-time access. Muốn dùng Java source import, package phải được exports cho module caller.

### Bài 7 — Public class, private constructor

```java
package demo.api;

public final class Token {
    private Token() {
    }

    public static Token of() {
        return new Token();
    }
}
```

Module đã export `demo.api`. App đã requires module. Caller có gọi `new Token()` được không?

**Đáp án:** **Không**, constructor private. `Token.of()` có thể được gọi và trả instance. Export package không làm private constructor thành public.

### Bài 8 — Package lồng tên

`exports com.example.api;` có export luôn `com.example.api.internal` không?

**Đáp án:** **Không**. Hai tên là hai package khác nhau. Nếu thật sự muốn cho phép client dùng public API của package thứ hai, cần exports riêng; thường package `internal` nên giữ kín và cung cấp facade.

### Bài 9 — Cùng module nhưng khác package

`module demo.lib { exports demo.api; }` chứa:
- `demo.api.PublicApi` là public;
- `demo.internal.Engine` là public;
- `demo.internal.Helper` là package-private.

`demo.api.PublicApi` có thể dùng `demo.internal.Engine` và `demo.internal.Helper` trực tiếp không?

**Đáp án:** Có thể dùng **`Engine`** vì cùng module, class public; không dùng trực tiếp **`Helper`** vì package-private và khác package. Không export `demo.internal` không chặn mã nội bộ module dùng public type của package này.

### Bài 10 — `requires transitive` không tự exports

Module facade dùng `requires transitive types.model;`. Module `types.model` chứa public class trong unexported package `types.internal`. Module app requires facade có tự import `types.internal.Secret` không?

**Đáp án:** **Không**. Readability transitive không xóa giới hạn exports. Module sở hữu package vẫn quyết định package nào là API công khai.

### Bài 11 — Cấu hình truy cập reflection

Một framework cần đọc private fields trong `company.entity` thuộc named module `company.data`. Có nên thêm `exports company.entity;` hay `opens company.entity to framework.module;`?

**Đáp án:** Nếu mục tiêu **deep reflection**, cân nhắc **`opens company.entity to framework.module;`** theo contract framework. `exports` đơn thuần không đủ để truy cập private member qua `setAccessible(true)`. Nếu framework còn cần import public types lúc biên dịch, đó là nhu cầu **exports riêng biệt** cần xét thêm.

## 29. Checklist khi chẩn đoán lỗi visibility trong module

1. **Xác định mã sử dụng có đang thuộc named module không?** Có `module-info.java` và chạy trên module path hay không?
2. **Xác định module chứa kiểu được dùng.** Đừng nhầm tên package với tên module.
3. **Kiểm tra readability:** module caller có `requires target.module;`, nhận đọc bắc cầu hay được cấu hình quan hệ đọc khác hợp lệ không?
4. **Kiểm tra exports:** package chứa kiểu có được module provider export cho module caller không?
5. **Kiểm tra qualified exports:** nếu có `to module.name`, module caller có đúng tên được liệt kê không?
6. **Kiểm tra public type:** top-level class/interface/record/enum được dùng từ ngoài package có access modifier phù hợp không?
7. **Kiểm tra member:** constructor, field, method có public/protected/package-private/private phù hợp tại vị trí gọi không?
8. **Kiểm tra package chính xác:** exports `a.b` không tự áp dụng cho `a.b.c`.
9. **Kiểm tra khác biệt opens/exports:** source import cần exports; deep reflection có thể cần opens.
10. **Kiểm tra compile-time receiver type:** method của runtime subclass không tự gọi được nếu kiểu tĩnh không khai báo thành viên.
11. **Kiểm tra cấu trúc module source/module path:** thư mục, `module-info.java`, tên module, tệp class được biên dịch đúng chưa?
12. **Kiểm tra classpath/automatic modules:** cách thư viện được nạp có thể làm thay đổi ranh giới exports so với explicit module.
13. **Không biến mọi thứ thành public/exported:** chỉ công bố các package và API mà consumer thực sự cần.
14. **Tránh phụ thuộc unexported packages:** thay vì `--add-exports` tràn lan, ưu tiên facade hoặc API có hợp đồng ổn định.
15. **Nếu dùng framework**, cấp qualified `opens` hẹp đúng package khi cần reflection; không tùy tiện mở toàn module.
16. **Chạy ví dụ trong môi trường sạch:** giữ các fixture mô-đun tách biệt, dùng `javac --module-source-path` và `java --module-path` tương ứng khi kiểm tra named modules.

## 30. Ghi nhớ

- **`public` là quyền truy cập của kiểu**, còn **`exports` là quyết định package nào được module công bố** cho module khác. Chúng là **hai tầng độc lập**.
- Module client thường phải **đọc được module thư viện** qua `requires` hoặc quan hệ readability hợp lệ, ngoài điều kiện `exports`.
- **Public class ở unexported package vẫn không là API import trực tiếp** cho module khác. Ngược lại, **package đã export không biến package-private class thành public**.
- **Constructor/field/method được kiểm tra riêng**: một public class trong exported package vẫn có thể có private constructor hoặc package-private method.
- **Qualified exports** (`exports p to m;`) chỉ công bố package cho module được nêu, không tự mở cho mọi consumer.
- **`opens` dành cho reflection runtime**, không tương đương `exports` cho source-level import. Deep reflection vào private member có thể cần `opens`.
- **`requires transitive` tác động lên readability**, không tự export những package của dependency.
- **Export không bao gồm package con theo tên**, và cùng module cũng không tự vượt được package-private/private access.
- Trong ứng dụng Java 17, luôn kiểm tra **kiểu**, **package**, **module readability**, **exports/opens** và **member access** trước khi kết luận một lời gọi hợp lệ.
