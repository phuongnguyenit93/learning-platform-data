# Quyền truy cập khi `record` nằm trong mô-đun (JPMS và Reflection)

## 1. Vấn đề cần giải quyết

Khi dùng `record` trong Java hiện đại, việc một lớp có modifier `public` **không tự động** đồng nghĩa mọi mô-đun khác đều có quyền dùng hoặc gọi các thành phần của nó bằng reflection. Java Platform Module System (JPMS) có thêm ranh giới **package/module** bên cạnh các modifier `public`, `private`, `protected` và package-private.

Một record thường có:

- Tên kiểu, header và các **record component**, ví dụ `record Employee(String name, int level)`.
- Constructor chuẩn (*canonical constructor*) để khởi tạo toàn bộ thành phần.
- Accessor public tương ứng với từng component, ví dụ `name()`, `level()`.
- Các trường lưu component là `private final` và những phương thức `equals`, `hashCode`, `toString` được sinh theo ngữ nghĩa record nếu không override.

Tuy nhiên, khi record nằm trong **named module**, quyền truy cập của mã ở mô-đun khác còn phụ thuộc vào `module-info.java`:

- **`requires`:** mô-đun dùng cần đọc mô-đun chứa record.
- **`exports`:** công bố package cho việc dùng kiểu `public` và các thành phần `public` theo ngữ nghĩa Java thông thường, kể cả reflection công khai.
- **`opens`:** cho phép **deep reflection** đến package được mở, chẳng hạn yêu cầu bỏ qua kiểm tra Java access bằng `setAccessible(true)`.
- **Không `exports` / không `opens`:** package được đóng với mô-đun khác, dù một lớp bên trong được khai báo `public`.

Record lần đầu xuất hiện dạng preview ở Java 14, nhưng **đã chính thức từ Java 16**. Reflection API `Class.isRecord()`, `Class.getRecordComponents()` và `java.lang.reflect.RecordComponent` được sử dụng ổn định trên JDK 17/21+. Bài sử dụng cú pháp chuẩn hiện hành, không cần `--enable-preview` hay giải pháp phụ thuộc preview cũ.

## 2. Đừng nhầm bốn lớp quyền truy cập

| Cơ chế | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| `public record` | Kiểu record có accessibility `public` ở cấp Java | `public record Employee(...) {}` |
| `requires module.name;` | Mô-đun người dùng đọc mô-đun được yêu cầu | `requires com.acme.records;` |
| `exports package.name;` | Cho phép mô-đun khác sử dụng các kiểu/thành phần `public` trong package | `exports com.acme.records.api;` |
| `opens package.name to module.name;` | Cho phép mô-đun được nêu làm **deep reflection** vào package tại runtime | `opens com.acme.records.internal to com.acme.records.consumer;` |

Có hai sự phân biệt quan trọng:

**Thứ nhất, `public` vẫn phải đi cùng ranh giới package.** Một `public record` trong package **không được export** sẽ không thể được mã ở mô-đun khác `import` và dùng trực tiếp, dù mô-đun kia có `requires`. Mô-đun đọc được mô-đun nguồn không có nghĩa là mọi package của nguồn đã được công bố.

**Thứ hai, `exports` khác `opens`.** `exports` chủ yếu cho **API công khai, truy cập tại biên dịch và runtime**; `opens` dành cho **reflection tại runtime**, kể cả khi reflection muốn truy cập thành phần không public bằng `setAccessible(true)`. `opens` một package **không** tự làm cho các kiểu trong package được phép `import` từ mô-đun khác. Có thể cấu hình cả hai khi cần, nhưng không nên mở nội bộ nếu không có lý do.

Lệnh `setAccessible(true)` **không phải chìa khóa vượt mọi ranh giới mô-đun**. Trong named module, JVM có thể từ chối yêu cầu khi package chưa được mở phù hợp, thường với `InaccessibleObjectException`.

## 3. Reflection nhìn thấy những gì của record?

Các API tiêu biểu:

```java
import java.lang.reflect.RecordComponent;

Class<?> type = SomeRecord.class;
boolean isRecord = type.isRecord();

if (isRecord) {
    for (RecordComponent component : type.getRecordComponents()) {
        System.out.println(component.getName());
        System.out.println(component.getType());
        System.out.println(component.getAccessor());
    }
}
```

Đây là **đoạn minh họa đặt trong một phương thức**, với `SomeRecord` là record mà mã gọi có thể tham chiếu hợp lệ. Các API:

- `Class.isRecord()` trả `true` nếu `Class<?>` mô tả một record.
- `Class.getRecordComponents()` trả **mảng `RecordComponent[]` theo thứ tự thành phần khai báo**; với lớp không phải record, kết quả là `null` (nên kiểm tra `isRecord()` trước).
- `RecordComponent.getName()` lấy tên thành phần, `getType()` lấy kiểu thô, `getGenericType()` trả thông tin kiểu tổng quát (nếu có).
- `RecordComponent.getAccessor()` lấy đối tượng `Method` tương ứng với accessor, ví dụ phương thức `name()` của `record Employee(String name, int level)`.
- `Class.getDeclaredConstructor(...)` tìm constructor theo kiểu tham số; `Constructor.newInstance(...)` gọi constructor bằng reflection.

**Đọc được metadata không đồng nghĩa có quyền gọi phương thức hoặc tạo đối tượng.** Việc sở hữu một đối tượng `Class<?>` hoặc `Method` chưa bỏ qua kiểm tra quyền truy cập. Với JPMS, bước gọi `Method.invoke(...)` / `Constructor.newInstance(...)` hoặc cố `setAccessible(true)` vẫn chịu quy tắc của module và package.

Điểm này đặc biệt quan trọng khi một framework phát hiện record bằng `isRecord()` rồi muốn tạo record qua canonical constructor. Framework cần có quyền thích hợp đối với package chứa record; việc phát hiện một record không tự cấp quyền thực thi mọi thao tác lên nó.

## 4. Ví dụ hoàn chỉnh: ba package, hai mô-đun

Để thấy khác biệt giữa `exports`, `opens` và package đóng, dùng dự án nhỏ có **hai named module**:

- `com.acme.records` chứa ba record trong ba package: API công khai, nội bộ mở cho reflection và package đóng.
- `com.acme.records.consumer` là mô-đun dùng record công khai, đồng thời thực hiện reflection thử nghiệm.

### 4.1 Cấu trúc tệp

```text
src/
├── com.acme.records/
│   ├── module-info.java
│   └── com/acme/records/
│       ├── api/Employee.java
│       ├── internal/InternalKey.java
│       └── secret/SecretKey.java
└── com.acme.records.consumer/
    ├── module-info.java
    └── com/acme/records/consumer/Main.java
```

Tên module và tên package ở ví dụ là tên minh họa. Cách tổ chức thư mục `src/<module-name>/...` được `javac --module-source-path` sử dụng.

### 4.2 Module cung cấp record

**`src/com.acme.records/module-info.java`**

```java
module com.acme.records {
    exports com.acme.records.api;
    opens com.acme.records.internal to com.acme.records.consumer;
}
```

Ba package có chính sách khác nhau:

1. `com.acme.records.api` **export** cho mọi mô-đun đọc `com.acme.records`.
2. `com.acme.records.internal` **open** cho riêng `com.acme.records.consumer` để mô-đun đó có thể làm deep reflection, nhưng không export.
3. `com.acme.records.secret` không xuất hiện trong `exports` hoặc `opens`, nên vẫn là package đóng với consumer.

**`src/com.acme.records/com/acme/records/api/Employee.java`**

```java
package com.acme.records.api;

public record Employee(String name, int level) {}
```

**`src/com.acme.records/com/acme/records/internal/InternalKey.java`**

```java
package com.acme.records.internal;

public record InternalKey(String code) {}
```

**`src/com.acme.records/com/acme/records/secret/SecretKey.java`**

```java
package com.acme.records.secret;

public record SecretKey(String code) {}
```

Cả ba record đều được khai báo `public`, đều có accessor và canonical constructor. **Chính module-info quyết định phạm vi mà mô-đun consumer có thể dùng chúng.** Trong ví dụ, record không khai báo thêm validation để việc thử quyền truy cập không bị lẫn với logic nghiệp vụ.

### 4.3 Module sử dụng record

**`src/com.acme.records.consumer/module-info.java`**

```java
module com.acme.records.consumer {
    requires com.acme.records;
}
```

`requires` cho consumer đọc mô-đun cung cấp. Nó không tự export các package `internal` và `secret`.

**`src/com.acme.records.consumer/com/acme/records/consumer/Main.java`**

```java
package com.acme.records.consumer;

import com.acme.records.api.Employee;
import java.lang.reflect.Constructor;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;

public class Main {
    public static void main(String[] args) throws Exception {
        Employee employee = new Employee("Lan", 3);
        System.out.println("exported.name=" + employee.name());
        System.out.println("exported.isRecord=" + Employee.class.isRecord());
        for (RecordComponent c : Employee.class.getRecordComponents()) {
            System.out.println("exported." + c.getName() + "="
                    + c.getAccessor().invoke(employee));
        }

        Class<?> internal =
                Class.forName("com.acme.records.internal.InternalKey");
        System.out.println("opened.isRecord=" + internal.isRecord());
        System.out.println("opened.component="
                + internal.getRecordComponents()[0].getName());
        Constructor<?> constructor =
                internal.getDeclaredConstructor(String.class);
        constructor.setAccessible(true);
        Object instance = constructor.newInstance("INT-7");
        Method accessor = internal.getDeclaredMethod("code");
        accessor.setAccessible(true);
        System.out.println("opened.value=" + accessor.invoke(instance));

        Class<?> secret =
                Class.forName("com.acme.records.secret.SecretKey");
        System.out.println("closed.isRecord=" + secret.isRecord());
        System.out.println("closed.component="
                + secret.getRecordComponents()[0].getName());
        try {
            secret.getDeclaredConstructor(String.class).setAccessible(true);
            System.out.println("closed.deepReflection=unexpected");
        } catch (InaccessibleObjectException ex) {
            System.out.println("closed.deepReflection=denied");
        }
    }
}
```

Giải thích:

- Có thể `import com.acme.records.api.Employee` và gọi `employee.name()` vì package `api` được `exports` và consumer có `requires`.
- `Employee.class.getRecordComponents()` nhận metadata; `getAccessor().invoke(employee)` gọi các accessor `public` thành công theo quyền truy cập công khai của package đã export.
- `Class.forName("com.acme.records.internal.InternalKey")` tìm lớp khi mô-đun đã được phân giải và lớp khả dụng cho class loader. Ta có thể kiểm tra `isRecord()` và metadata. Package `internal` không export, nhưng đã `opens ... to com.acme.records.consumer` nên `setAccessible(true)` cho canonical constructor và accessor được phép, rồi `newInstance`/`invoke` thành công.
- `Class.forName("com.acme.records.secret.SecretKey")` vẫn có thể lấy đối tượng `Class<?>` trong bố cục chạy minh họa. Việc đọc metadata `code` **không cấp quyền deep reflection**. `setAccessible(true)` đối với constructor của `SecretKey` bị từ chối vì package `secret` không export hoặc open cho consumer.
- Bắt `InaccessibleObjectException` cho thấy **thiếu quyền ở ranh giới module**; không nên coi đây là lỗi constructor do record hay vì tham số `"INT-7"`.

### 4.4 Biên dịch và chạy

Đặt terminal tại thư mục chứa `src`. Dùng JDK 17 trở lên. Lệnh dưới đây liệt kê rõ các tệp, nên không phụ thuộc trình shell có hỗ trợ glob mở rộng hay không:

```bash
javac --release 17 -encoding UTF-8 --module-source-path src -d mods \
  src/com.acme.records/module-info.java \
  src/com.acme.records/com/acme/records/api/Employee.java \
  src/com.acme.records/com/acme/records/internal/InternalKey.java \
  src/com.acme.records/com/acme/records/secret/SecretKey.java \
  src/com.acme.records.consumer/module-info.java \
  src/com.acme.records.consumer/com/acme/records/consumer/Main.java

java --module-path mods \
  -m com.acme.records.consumer/com.acme.records.consumer.Main
```

Lệnh nhiều dòng dùng dấu `\` để nối dòng theo shell Bash; trên PowerShell/Windows có thể viết mỗi lệnh thành **một dòng** và giữ nguyên các đường dẫn tương ứng. Cú pháp Java `--module-source-path`, `--module-path` và `-m` là chung cho các nền tảng.

**Stdout chính xác:**

```text
exported.name=Lan
exported.isRecord=true
exported.name=Lan
exported.level=3
opened.isRecord=true
opened.component=code
opened.value=INT-7
closed.isRecord=true
closed.component=code
closed.deepReflection=denied
```

Ví dụ đã kiểm thử với trình biên dịch ở chế độ `--release 17`: cả hai module biên dịch thành công, chương trình chạy được và sinh ra đúng 10 dòng trên.

## 5. So sánh hai thao tác: xem metadata và sử dụng thành phần

Một hệ thống quét kiểu có thể làm hai việc rất khác nhau:

**Chỉ mô tả cấu trúc record:**

```java
Class<?> type =
        Class.forName("com.acme.records.secret.SecretKey");

if (type.isRecord()) {
    for (RecordComponent c : type.getRecordComponents()) {
        System.out.println(c.getName() + ": "
                + c.getType().getSimpleName());
    }
}
```

Đây là đoạn nằm trong một phương thức, giả định module đã được phân giải và `Class.forName` nạp được lớp. Trong ví dụ, nó có thể in `code: String` dù package `secret` chưa mở. Khả năng truy vấn metadata **không phải** bảo đảm quyền truy cập phương thức hoặc constructor.

**Khởi tạo đối tượng bằng reflection:**

```java
Class<?> type =
        Class.forName("com.acme.records.internal.InternalKey");
var ctor = type.getDeclaredConstructor(String.class);
ctor.setAccessible(true); // Được phép vì package đã opens cho module này.
Object obj = ctor.newInstance("ABC");
```

Cùng thao tác `setAccessible(true)` trên constructor của `SecretKey` trong package đóng sẽ bị từ chối trong ví dụ. Đặc biệt, **đừng bắt mọi lỗi `InaccessibleObjectException` rồi lặng lẽ bỏ qua**: cần xác định cấu hình module, package, đối tượng cần truy cập và nơi thực hiện reflection.

### Các trường hợp cần phân biệt

| Thao tác | Package chỉ `exports` | Package chỉ `opens` cho caller | Package không `exports` và không `opens` |
| --- | --- | --- | --- |
| Import và dùng `public record` ở compile time | Có, nếu module đọc được | Không | Không |
| Gọi public constructor/accessor bằng API Java thông thường | Có | Không thể viết tham chiếu trực tiếp từ module khác | Không |
| Reflection vào public member với kiểm tra truy cập bình thường | Có, với public class/member | Không nên giả định; dùng cơ chế deep reflection nếu cần | Không |
| `setAccessible(true)` cho private member hay constructor của non-exported public type | Không chỉ nhờ `exports` | Có thể được phép cho caller đã được mở đúng package | Bị từ chối theo strong encapsulation |
| Đọc metadata record khi đã có `Class<?>` | Có thể | Có thể | Có thể, nhưng không cấp quyền sử dụng |

Trong bảng, "có thể" về metadata nghĩa là **sau khi đã lấy được đối tượng Class**. Việc tìm/khởi tạo lớp còn phụ thuộc module resolution, class loader, lớp tồn tại hay không và các điều kiện runtime khác.

## 6. Record component có `private final`: `opens` không làm nó mutable

Đối với:

```java
public record Employee(String name, int level) {}
```

Java sinh các trường lưu trữ component `private final` (tương ứng với `name` và `level`) và các accessor public `name()`, `level()`. Nếu một module có quyền deep reflection thích hợp, reflection có thể **đọc** các trường private khi các kiểm tra access được cho phép. Tuy nhiên, **final field của record là non-modifiable final field** theo API reflection: `setAccessible(true)` không trao quyền ghi lại component đã được khởi tạo.

Ví dụ sau chỉ **minh họa ý định không hợp lệ** chứ không phải chương trình nên chạy:

```java
// Không dùng reflection để cập nhật component của record.
var field = Employee.class.getDeclaredField("name");
field.setAccessible(true); // Còn phụ thuộc package/module access.
field.set(employee, "Khác"); // Không hợp lệ: trường component final của record.
```

Trong Java hiện đại, muốn "thay đổi" dữ liệu một record, hãy **tạo record mới** bằng constructor thích hợp. Đừng thiết kế framework dựa trên giả định rằng có thể khởi tạo rỗng rồi điền component qua reflection giống một bean có setter.

## 7. Nếu framework cần reflection: mở package nào?

Khi triển khai serializer, mapper, dependency injection, ORM, validator hoặc thư viện tạo đối tượng từ metadata, cần xác định **phạm vi reflection thực sự**:

1. **Đọc/ghi qua API công khai và canonical constructor của public record:** nếu framework có thể hoạt động bằng các API public, mô hình sử dụng `exports` và lời gọi public phù hợp thường là điểm xuất phát rõ ràng. Không tự động mở toàn bộ module nếu chưa cần.
2. **Framework cần `setAccessible(true)` vào loại/member không công khai hoặc package không export:** cần cân nhắc `opens` package đó đến **tên module của framework** nếu tích hợp cho phép. Trong ví dụ, tên consumer là `com.acme.records.consumer`; dự án thực tế phải dùng đúng tên module đích.
3. **Chỉ một vài module được phép deep reflection:** ưu tiên `opens some.package to target.module;` thay vì mở cho mọi module.
4. **Package là API dùng trực tiếp bởi người tiêu thụ:** công bố bằng `exports` (nếu cần), không thay `exports` bằng `opens` rồi mong mã bên ngoài có thể `import` kiểu.
5. **Framework có hỗ trợ record theo constructor binding:** ưu tiên cơ chế đó khi phù hợp; không giả định framework cần sửa trường `private final` bằng reflection.

Ví dụ lược đồ module (chỉ minh họa cú pháp, các tên không phải API của một framework cụ thể):

```java
module demo.domain {
    exports demo.domain.api;
    opens demo.domain.dto to demo.serializer;
}
```

Lược đồ trên giả định hai package `demo.domain.api` và `demo.domain.dto` thực sự tồn tại, cùng một named module có tên `demo.serializer` được dùng để truy cập theo reflection. Khi dùng Java module path, cần cấu hình các module sao cho mô-đun liên quan được phân giải đúng.

**Không mở cả module chỉ để khắc phục một lỗi đơn lẻ.** Java hỗ trợ cú pháp `open module ...` cho phép deep reflection vào mọi package, nhưng chính sách này rộng hơn `opens some.package to ...`; khi xử lý dữ liệu nhạy cảm hoặc mô-đun thư viện, nên ưu tiên mở phạm vi tối thiểu.

## 8. Vì sao `--add-opens` không phải thiết kế mặc định?

Một số dự án cũ hoặc thư viện chưa được cấu hình đầy đủ dùng JVM option `--add-opens` để mở package tại runtime. Cơ chế này có thể hữu ích trong quá trình thử nghiệm, tương thích có kiểm soát hoặc di chuyển hệ thống, nhưng **không nên xem là thay thế lâu dài cho thiết kế `module-info.java` đúng đắn** nếu bạn kiểm soát mã nguồn module.

Ví dụ cú pháp minh họa:

```bash
java --add-opens com.acme.records/com.acme.records.secret=com.acme.records.consumer \
  --module-path mods \
  -m com.acme.records.consumer/com.acme.records.consumer.Main
```

Tùy option mở package, **chương trình kiểm thử ở trên có thể đổi kết quả** tại bước `closed.deepReflection`. Đây là hành vi mong đợi khi cấp thêm quyền runtime, chứ không chứng minh package được export hoặc cho phép import từ source. Không sử dụng option này nếu không hiểu mô-đun nguồn, package, mô-đun đích và tác động đến strong encapsulation.

Không dùng `--illegal-access` như một giải pháp cho code mới: hãy dùng `exports`/`opens`, API public hoặc cấu hình framework đúng phiên bản Java hiện đại. `--illegal-access` không còn là cách làm thích hợp để dựa vào trên JDK hiện hành.

## 9. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách tiếp cận |
| --- | --- | --- |
| Không thể `import` public record trong named module khác | Package chưa `exports`, dù module đã `requires` | Cấu hình `exports` (có thể qualified exports) nếu loại đó là API |
| `Class.forName` thất bại | Module chưa được phân giải, tên lớp sai, class loader không thấy lớp | Kiểm tra module path, `requires`, package/class name, loader |
| `Class.isRecord()` trả `true` nhưng `Method.invoke` lỗi | Metadata và quyền thực thi là hai bước khác nhau | Kiểm tra package `exports`/`opens` và Java access của member |
| `setAccessible(true)` ném `InaccessibleObjectException` | Package không mở cho module gọi | Giới hạn việc phản chiếu hoặc bổ sung `opens ... to ...` phù hợp |
| Cấp `opens` nhưng import vẫn lỗi | `opens` không công bố API ở compile time | Cân nhắc `exports` nếu thực sự cần tham chiếu trực tiếp |
| Dùng `exports` rồi cố đọc private field bằng deep reflection | `exports` không tự cho phép bỏ qua `private` | Dùng API public, hoặc `opens` phạm vi thích hợp nếu cần |
| Cố dùng `Field.set(...)` để sửa component của record | Trường component là non-modifiable `final` | Tạo instance record mới |
| Thấy `getRecordComponents() == null` rồi duyệt như mảng | Kiểu đang xét không phải record | Kiểm tra `isRecord()` hoặc `null` trước |
| Mở mọi package bằng `open module` khi chỉ cần một DTO | Cấp quyền reflection quá rộng | Mở package và module đích ở phạm vi tối thiểu |

Để chẩn đoán access error, cần phân biệt **lỗi biên dịch**, **`IllegalAccessException` khi gọi reflection**, và **`InaccessibleObjectException` khi thử làm accessible một member**. Các lỗi có thể có thông điệp khác nhau nhưng cần xử lý theo quyền truy cập cụ thể, không thay `setAccessible` một cách máy móc.

## 10. Thử kiểm tra quyền ở runtime bằng API module

Ngoài `module-info.java`, Java cung cấp một số API để kiểm tra trạng thái của một module:

```java
Module owner = Employee.class.getModule();
Module caller = Main.class.getModule();

System.out.println(owner.isExported(
        "com.acme.records.api", caller));
System.out.println(owner.isOpen(
        "com.acme.records.internal", caller));
System.out.println(owner.isOpen(
        "com.acme.records.secret", caller));
```

Đoạn này **chỉ áp dụng trong lớp `Main` của ví dụ đa mô-đun** ở trên và có các kiểu đã được import. Với khai báo `module-info.java` như trên, ba giá trị lần lượt là:

```text
true
true
false
```

`Module.isExported(packageName, otherModule)` kiểm tra package có export cho mô-đun đích hay không; `Module.isOpen(packageName, otherModule)` kiểm tra package có mở cho mô-đun đích hay không. Chúng hữu ích để làm rõ các giả định access, nhưng **không tự mở package** và không thay thế việc kiểm tra actual invocation. Việc một module có quyền mở package không có nghĩa mọi lời gọi reflection đều thành công: đối tượng, chữ ký phương thức, tham số và quy tắc reflection khác vẫn phải đúng.

## 11. Quy trình gợi ý khi viết mã với record trong module

1. **Xác định record nào là API công khai.** Record nằm trong package export nếu mô-đun khác cần import và gọi accessor/constructor ở cấp Java thông thường.
2. **Xác định ai thực hiện reflection và mục đích.** Chỉ đọc metadata qua `Class.isRecord()`/`getRecordComponents()` hay cần thật sự tạo instance và truy cập member?
3. **Chọn `exports` hay `opens` theo nhu cầu**, không dùng một trong hai như từ đồng nghĩa. Dùng `opens ... to ...` khi chỉ một module được phép deep reflection.
4. **Giữ các component ở trạng thái hợp lệ khi tạo**. Record có thể dùng compact constructor để validate/normalize, không dựa vào việc sửa `private final` bằng reflection sau khi tạo.
5. **Kiểm thử trên module path thực sự**. Chạy bài test trên classpath có thể làm mất bối cảnh của named module và che giấu lỗi cấu hình `exports`/`opens`. Với JPMS, nên biên dịch/chạy bằng `--module-source-path`, `--module-path` và `-m` như ví dụ.
6. **Kiểm thử ít nhất ba nhóm:** package exported, package chỉ opened cho reflective caller, package đóng; so sánh metadata discovery với việc thực sự gọi constructor/accessor.

**Ghi nhớ:** Record vẫn chịu đầy đủ quy tắc quyền truy cập Java và JPMS. `public` quy định khả năng truy cập ở cấp lớp/member; `requires` xác định quan hệ đọc module; `exports` công bố API; `opens` cho phép deep reflection ở runtime. Có thể thấy metadata của một record mà vẫn **không có quyền tạo hoặc truy cập instance**, và `setAccessible(true)` không tự vượt strong encapsulation. Thiết kế module đúng phạm vi là cách an toàn và bền vững trên Java hiện đại.

### Tài liệu tham khảo chính thức

- [Java Language Specification — Record Classes (JLS `8.10)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java Language Specification — Modules (JLS `7.7)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7)
- [Java Platform Module System — ModuleDescriptor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [Java SE — RecordComponent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Java SE — AccessibleObject.setAccessible](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html#setAccessible(boolean))
