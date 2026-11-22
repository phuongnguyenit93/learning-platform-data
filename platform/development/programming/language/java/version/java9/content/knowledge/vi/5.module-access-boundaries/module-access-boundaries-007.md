# `canAccess` và `trySetAccessible` trong mã phản chiếu

Từ Java 9, API Reflection có hai phương thức giúp kiểm tra và xử lý quyền truy cập thành viên một cách rõ ràng: `AccessibleObject.canAccess(Object)` và `AccessibleObject.trySetAccessible()`. Chúng đặc biệt quan trọng khi ứng dụng dùng Java Platform Module System (JPMS), vì quyền truy cập phản chiếu sâu vào thành viên `private` còn phụ thuộc vào ranh giới mô-đun và trạng thái `opens` của package.

`canAccess` trả lời câu hỏi **mã đang gọi có thể truy cập thành viên này ngay lúc hiện tại không?**. `trySetAccessible` thử bật cờ bỏ qua kiểm tra truy cập Java thông thường cho đối tượng phản chiếu; phương thức trả về `true` nếu thành công và `false` nếu quy tắc truy cập mô-đun không cho phép.

## 1. Vị trí của hai phương thức trong Reflection API

`AccessibleObject` là lớp cha của các đối tượng phản chiếu đại diện cho thành viên lớp, bao gồm:

- `Field`: trường dữ liệu.
- `Method`: phương thức.
- `Constructor`: hàm khởi tạo.

Vì vậy, `canAccess` và `trySetAccessible` có thể dùng với cả ba loại đối tượng trên.

```java
Field field = Customer.class.getDeclaredField("name");
Method method = Customer.class.getDeclaredMethod("calculate");
Constructor<?> constructor = Customer.class.getDeclaredConstructor(String.class);
```

`getDeclaredField`, `getDeclaredMethod` và `getDeclaredConstructor` tìm thành viên được khai báo trực tiếp trong lớp, kể cả thành viên không `public`. Việc tìm thấy một thành viên không đồng nghĩa mã gọi đã có quyền đọc, ghi hoặc gọi thành viên đó.

## 2. `canAccess(Object obj)` — kiểm tra quyền truy cập hiện tại

`canAccess` kiểm tra liệu lớp đang gọi có thể truy cập thành viên phản chiếu theo quy tắc truy cập Java hiện hành hay không. Phương thức chỉ kiểm tra; nó không bật quyền truy cập và không thay đổi trạng thái của đối tượng phản chiếu.

```java
boolean accessible = field.canAccess(customer);
```

Kết quả:

- `true`: lớp gọi có thể truy cập thành viên ở thời điểm kiểm tra. Điều này có thể do quyền truy cập thông thường cho phép hoặc cờ bỏ qua kiểm tra đã được bật trước đó.
- `false`: quyền truy cập hiện tại không cho phép lớp gọi truy cập thành viên.

### Truyền đối tượng receiver đúng cách

Tham số `obj` mô tả đối tượng mà thành viên instance sẽ được truy cập:

| Thành viên phản chiếu | Giá trị truyền vào `canAccess` |
| --- | --- |
| Field instance | Instance của lớp khai báo field |
| Method instance | Instance của lớp khai báo method |
| Field hoặc method `static` | `null` (tham số bị bỏ qua với thành viên static) |
| Constructor | `null` |

Nếu truyền `null` cho field hoặc method instance, hoặc truyền một đối tượng không tương thích với lớp khai báo thành viên, phương thức ném `IllegalArgumentException`. Với constructor, `obj` phải là `null`.

Ví dụ:

```java
Customer customer = new Customer("Ada");
Field name = Customer.class.getDeclaredField("name");
Method instanceMethod = Customer.class.getDeclaredMethod("display");
Method staticMethod = Customer.class.getDeclaredMethod("createDefault");
Constructor<?> constructor = Customer.class.getDeclaredConstructor(String.class);

name.canAccess(customer);          // field instance
instanceMethod.canAccess(customer); // method instance
staticMethod.canAccess(null);       // method static
constructor.canAccess(null);        // constructor
```

Các dòng trên minh họa cách truyền receiver; tên thành viên phải tồn tại trong lớp thực tế mà bạn kiểm tra.

## 3. `trySetAccessible()` — thử cho phép truy cập sâu

`trySetAccessible()` thử bật cờ `accessible` để bỏ qua kiểm tra truy cập ngôn ngữ Java đối với đối tượng phản chiếu hiện tại.

```java
boolean enabled = field.trySetAccessible();
```

- Trả về `true` nếu quyền bỏ qua kiểm tra truy cập được bật thành công.
- Trả về `false` nếu quyền đó không thể được bật theo quy tắc đóng gói mô-đun.

Khi trả về `true`, các thao tác phản chiếu tiếp theo trên đối tượng đó có thể truy cập thành viên theo cơ chế đã được cho phép. Khi trả về `false`, không được giả định rằng có thể đọc hoặc gọi thành viên; thao tác như `Field.get` hoặc `Method.invoke` vẫn có thể ném `IllegalAccessException`.

`trySetAccessible` chỉ thay đổi trạng thái của đối tượng `Field`, `Method` hoặc `Constructor` mà bạn gọi. Nó không thay đổi modifier của thành viên trong mã nguồn, không mở package cho mọi mô-đun và không cấp quyền cho các đối tượng phản chiếu khác.

## 4. JPMS: `exports` và `opens` có vai trò khác nhau

Với các lớp thuộc những mô-đun khác nhau, quyền truy cập phản chiếu sâu chịu sự kiểm soát của JPMS:

- `exports` cho phép mô-đun khác truy cập các kiểu `public` trong package được export theo quy tắc truy cập Java thông thường.
- `opens` cho phép mã ở mô-đun được chỉ định truy cập phản chiếu sâu vào các kiểu và thành viên trong package ở runtime, kể cả thành viên không `public`.

Do đó, export một package không tự động cho phép `trySetAccessible()` thành công đối với field `private` trong package đó. Khi cần phản chiếu sâu giữa hai named module, package chứa lớp đích phải được mở cho mô-đun gọi.

### Mở package có phạm vi bằng `opens`

Ví dụ mô-đun chứa lớp dữ liệu:

```java
module com.example.model {
    exports com.example.model;
    opens com.example.model to com.example.reflector;
}
```

`exports` phục vụ việc sử dụng API công khai lúc biên dịch; `opens` cấp quyền phản chiếu sâu ở runtime cho `com.example.reflector`. Có thể chỉ định `opens` cho đúng package và đúng mô-đun cần quyền.

### Mở package khi khởi chạy bằng `--add-opens`

Nếu không thể sửa `module-info.java`, có thể cấu hình quyền mở package ở runtime:

```bash
java --module-path out \
  --add-opens com.example.model/com.example.model=com.example.reflector \
  --module com.example.reflector/com.example.reflector.Main
```

Cú pháp là `--add-opens source.module/package=target.module`. Đây là cấu hình runtime; nó không sửa descriptor của JAR. Nên ưu tiên khai báo `opens` có phạm vi trong descriptor khi quyền phản chiếu là một phần thiết kế ổn định của ứng dụng. Dùng `--add-opens` cho tích hợp, kiểm thử hoặc cấu hình triển khai cần thiết.

Không nên mở toàn bộ package hoặc toàn bộ mô-đun rộng hơn nhu cầu. Mở package làm tăng bề mặt truy cập phản chiếu và giảm mức đóng gói mà JPMS cung cấp.

## 5. Ví dụ hoàn chỉnh: kiểm tra và bật truy cập field `private`

Ví dụ có hai mô-đun. `com.example.model` chứa lớp `Customer`; `com.example.reflector` tìm field `private name`, kiểm tra quyền và thử bật truy cập sâu.

### Cấu trúc thư mục

```text
src/
├── com.example.model/
│   ├── module-info.java
│   └── com/example/model/Customer.java
└── com.example.reflector/
    ├── module-info.java
    └── com/example/reflector/Main.java
```

### `com.example.model/module-info.java`

```java
module com.example.model {
    exports com.example.model;
    opens com.example.model to com.example.reflector;
}
```

### `com.example.model/com/example/model/Customer.java`

```java
package com.example.model;

public final class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }
}
```

### `com.example.reflector/module-info.java`

```java
module com.example.reflector {
    requires com.example.model;
}
```

### `com.example.reflector/com/example/reflector/Main.java`

```java
package com.example.reflector;

import com.example.model.Customer;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        Customer customer = new Customer("Ada");
        Field name = Customer.class.getDeclaredField("name");

        System.out.println("canAccess before = " + name.canAccess(customer));
        boolean enabled = name.trySetAccessible();
        System.out.println("trySetAccessible = " + enabled);
        System.out.println("canAccess after = " + name.canAccess(customer));

        if (enabled) {
            System.out.println("name = " + name.get(customer));
        }
    }
}
```

### Biên dịch và chạy

Chạy từ thư mục gốc chứa `src/` bằng JDK 9 trở lên. Tạo thư mục output trước khi biên dịch:

```bash
mkdir -p out
javac --module-source-path src -d out -m com.example.model,com.example.reflector
java --module-path out --module com.example.reflector/com.example.reflector.Main
```

Trên PowerShell, lệnh tạo thư mục tương đương là:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
```

Kết quả khi package đã được mở cho mô-đun gọi:

```text
canAccess before = false
trySetAccessible = true
canAccess after = true
name = Ada
```

Ban đầu `canAccess` trả về `false` vì field là `private` và cờ bỏ qua kiểm tra chưa được bật. `trySetAccessible` thành công vì `com.example.model` mở package cho `com.example.reflector`. Sau đó `canAccess` trả về `true` và `Field.get` đọc được giá trị.

### Khi package không được mở

Nếu bỏ dòng `opens com.example.model to com.example.reflector;` khỏi `module-info.java` của `com.example.model`, rồi biên dịch lại vào một thư mục output sạch, kết quả là:

```text
canAccess before = false
trySetAccessible = false
canAccess after = false
```

Chương trình không gọi `Field.get` vì `enabled` là `false`. Đây là cách xử lý an toàn khi quyền truy cập sâu không được cấp.

Nếu vẫn cần quyền truy cập cho lần chạy đó, giữ descriptor không có `opens` và chạy với tùy chọn:

```bash
java --module-path out \
  --add-opens com.example.model/com.example.model=com.example.reflector \
  --module com.example.reflector/com.example.reflector.Main
```

Kết quả khi chạy với `--add-opens` giống trường hợp đã khai báo `opens`: `trySetAccessible = true` và giá trị `Ada` được đọc thành công.

## 6. Xử lý kết quả và ngoại lệ

| Tình huống | Cách xử lý |
| --- | --- |
| `canAccess` trả về `true` | Có thể truy cập thành viên theo trạng thái hiện tại; thực hiện thao tác phản chiếu phù hợp. |
| `canAccess` trả về `false` | Kiểm tra modifier, receiver và ranh giới mô-đun trước khi truy cập. |
| `trySetAccessible` trả về `true` | Tiếp tục thao tác phản chiếu; chỉ đối tượng phản chiếu hiện tại được bật cờ. |
| `trySetAccessible` trả về `false` | Không thực hiện thao tác cần quyền sâu; xem xét `opens` hoặc `--add-opens` nếu thiết kế cho phép. |
| `canAccess` nhận receiver không hợp lệ | Sửa đối tượng truyền vào; phương thức ném `IllegalArgumentException`. |
| Thao tác `get`/`invoke` không được phép | Xử lý `IllegalAccessException`; kiểm tra lại quyền truy cập trước thao tác. |

`trySetAccessible` cho phép xử lý trường hợp không được mở package bằng một nhánh điều kiện rõ ràng. Phương thức `setAccessible(true)` vẫn có trong API nhưng có thể ném `InaccessibleObjectException` nếu không thể bật quyền; chỉ dùng khi ứng dụng chủ động muốn xử lý ngoại lệ đó.

## 7. Phân biệt `canAccess` với `isAccessible`

`AccessibleObject.isAccessible()` đã deprecated từ Java 9. Tên phương thức dễ gây hiểu nhầm: nó phản ánh cờ bỏ qua kiểm tra truy cập đã được bật hay chưa, không trả lời câu hỏi lớp gọi có quyền truy cập thành viên theo quy tắc hiện tại hay không.

Với mã mới:

- Dùng `canAccess(receiver)` để kiểm tra quyền truy cập hiện tại.
- Dùng `trySetAccessible()` khi thực sự cần bật quyền truy cập sâu và muốn xử lý trường hợp thất bại bằng giá trị boolean.

Không dùng `isAccessible()` thay cho `canAccess()`, và không gọi `trySetAccessible()` một cách máy móc cho mọi thành viên. API công khai nên được sử dụng theo quyền truy cập Java thông thường.

## 8. Lưu ý thiết kế và bảo mật

1. **Ưu tiên API công khai.** Reflection sâu nên dành cho framework, serializer, dependency injection hoặc tích hợp có yêu cầu cụ thể.
2. **Mở đúng package và đúng mô-đun.** Qualified `opens` thu hẹp phạm vi quyền so với mở toàn bộ mô-đun.
3. **Kiểm tra boolean trước khi đọc hoặc gọi.** Nếu `trySetAccessible()` trả về `false`, đừng tiếp tục thao tác cần quyền truy cập sâu.
4. **Không nhầm readability với reflection access.** `requires` cho phép mô-đun đọc mô-đun khác; `exports` và `opens` kiểm soát quyền truy cập package theo từng mục đích.
5. **Không dựa vào package nội bộ của JDK.** Các package nội bộ không phải API công khai ổn định; cơ chế đóng gói mô-đun hiện hành bảo vệ chúng khỏi truy cập trái phép.
6. **Giữ quyền truy cập ở phạm vi tối thiểu.** Không mở package rộng chỉ để né một lỗi truy cập; xác định đúng mô-đun gọi và thành viên cần dùng.

## 9. Ghi nhớ

- `canAccess(obj)` kiểm tra khả năng truy cập hiện tại và không thay đổi quyền.
- `trySetAccessible()` thử bật quyền bỏ qua kiểm tra truy cập và trả về `true` hoặc `false`.
- Với field/method instance, truyền receiver tương ứng; với thành viên static và constructor, truyền `null`.
- Trong JPMS, `exports` phục vụ API công khai; `opens` phục vụ phản chiếu sâu ở runtime.
- Nếu package chưa mở, cân nhắc qualified `opens` hoặc `--add-opens` có phạm vi rõ ràng.

## Tài liệu tham khảo

- [Java SE 17 API — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java SE 17 API — `Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java Language Specification — Module Declarations and `opens`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)