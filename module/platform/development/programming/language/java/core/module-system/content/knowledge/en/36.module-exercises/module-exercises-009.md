# Kiểm thử `--add-opens`, reflection và strong encapsulation

## Mục tiêu

Sau bài thực hành này, bạn có thể tạo một module có package nội bộ, chứng minh deep reflection bị chặn khi package chưa được mở, chạy lại với `--add-opens`, phân biệt target là named module hay `ALL-UNNAMED`, kiểm tra trạng thái bằng Reflection và Module API, đồng thời cấu hình đúng JVM arguments cho test runner.

## 1. Mô hình kiểm thử

Ta tạo module `com.acme.domain` có package API và package implementation nội bộ. Một chương trình probe đóng vai trò framework, dùng reflection để đọc private field trong package nội bộ.

Cấu trúc:

~~~text
project/
  src/
    com.acme.domain/
      module-info.java
      com/acme/domain/internal/Customer.java
  probe/
    ReflectionProbe.java
  mods/
  probe-classes/
~~~

Descriptor chỉ export API package:

~~~java
module com.acme.domain {
    exports com.acme.domain.api;
}
~~~

Class trong package nội bộ:

~~~java
package com.acme.domain.internal;

public final class Customer {
    private final String name;

    public Customer(String name) {
        this.name = name;
    }
}
~~~

Package `com.acme.domain.internal` không được export và cũng chưa được open. Class có modifier `public`, nhưng điều đó không tự động cho module khác quyền truy cập package.

## 2. Tạo ReflectionProbe trên class path

Tạo file `probe/ReflectionProbe.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Class<?> type =
                Class.forName("com.acme.domain.internal.Customer");

        Constructor<?> constructor =
                type.getDeclaredConstructor(String.class);

        boolean constructorOpen = constructor.trySetAccessible();
        System.out.println("constructor accessible = " + constructorOpen);

        if (!constructorOpen) {
            throw new IllegalStateException(
                    "Customer constructor is not open to this module");
        }

        Object customer = constructor.newInstance("Ada");

        Field name = type.getDeclaredField("name");
        boolean fieldOpen = name.trySetAccessible();
        System.out.println("field accessible = " + fieldOpen);

        if (!fieldOpen) {
            throw new IllegalStateException(
                    "Customer.name is not open to this module");
        }

        System.out.println("name = " + name.get(customer));
    }
}
~~~

Probe dùng tên class dạng chuỗi nên không cần import class từ package nội bộ. Nó kiểm tra cả constructor và field vì framework có thể cần tạo object và đọc trạng thái object bằng reflection.

`trySetAccessible()` trả về `false` nếu quyền truy cập không thể được mở. Nếu dùng `setAccessible(true)`, thao tác có thể ném `InaccessibleObjectException` khi module boundary không cho phép deep reflection.

## 3. Biên dịch và chạy khi package chưa được mở

Từ thư mục `project`, biên dịch module domain:

~~~bash
javac -d mods --module-source-path src -m com.acme.domain
~~~

Biên dịch probe:

~~~bash
javac -d probe-classes probe/ReflectionProbe.java
~~~

Chạy probe với module domain được resolve:

~~~bash
java --module-path mods --add-modules com.acme.domain --class-path probe-classes ReflectionProbe
~~~

`--add-modules com.acme.domain` đưa module domain vào graph khởi động, dù main class của probe nằm trên class path. Probe thuộc unnamed module của application class loader.

Vì package nội bộ chưa được export hoặc open cho unnamed module, `trySetAccessible()` trên constructor sẽ trả về `false`. Chương trình dừng với thông báo do probe tạo ra. Đây là kết quả mong đợi của bước đầu tiên.

Có thể đổi probe sang `constructor.setAccessible(true)` để quan sát exception trực tiếp. Khi package không được mở cho caller, JVM có thể ném `InaccessibleObjectException`. Exception message thường nêu source module, package và target module; đó là bằng chứng để viết option mở đúng phạm vi.

## 4. Mở package cho unnamed module bằng ALL-UNNAMED

Chạy lại với:

~~~bash
java --module-path mods --add-modules com.acme.domain --add-opens com.acme.domain/com.acme.domain.internal=ALL-UNNAMED --class-path probe-classes ReflectionProbe
~~~

Kết quả dự kiến:

~~~text
constructor accessible = true
field accessible = true
name = Ada
~~~

Cách đọc option:

~~~text
--add-opens source-module/package=target-module
~~~

- `com.acme.domain` là module sở hữu package.
- `com.acme.domain.internal` là package cần mở.
- `ALL-UNNAMED` là target gồm các unnamed module.

`ALL-UNNAMED` không có nghĩa là mở tất cả package hoặc toàn bộ module. Nó chỉ cấp quyền cho target unnamed modules đối với package được chỉ định. Nếu framework nằm trên class path, đây thường là target phù hợp.

## 5. Kiểm thử với framework là named module

Nếu framework được đặt trên module path, hãy chỉ định tên module của framework thay vì `ALL-UNNAMED`.

Ví dụ descriptor cho probe module:

~~~java
module com.acme.framework {
    requires com.acme.domain;
}
~~~

Probe vẫn dùng `Class.forName("com.acme.domain.internal.Customer")`, nên không cần import class nội bộ. Dependency `requires` giúp framework module đọc module domain; package nội bộ vẫn không được export.

Sau khi biên dịch framework vào module path, chạy:

~~~bash
java --module-path mods --add-opens com.acme.domain/com.acme.domain.internal=com.acme.framework --module com.acme.framework/com.acme.framework.ReflectionProbe
~~~

Target trong option là `com.acme.framework`, vì code thực hiện reflection thuộc named module này.

Nếu mở cho sai target module, probe vẫn không có quyền deep reflection. Xác định module thật của class framework:

~~~java
Module frameworkModule = FrameworkEntryPoint.class.getModule();

System.out.println("name = " + frameworkModule.getName());
System.out.println("named = " + frameworkModule.isNamed());
~~~

Nếu `isNamed()` trả về `false`, class đang thuộc unnamed module và target tương ứng trong JVM option là `ALL-UNNAMED`.

## 6. Kiểm tra quyền truy cập bằng Module API

Có thể in trạng thái module và kiểm tra package open từ probe:

~~~java
Module source = type.getModule();
Module target = ReflectionProbe.class.getModule();

System.out.println("source module = " + source.getName());
System.out.println("target module = "
        + (target.isNamed() ? target.getName() : "<unnamed>"));

boolean open = source.isOpen(
        "com.acme.domain.internal",
        target);

System.out.println("package open = " + open);
~~~

Gọi `isOpen(packageName, targetModule)` trên module sở hữu package. Nếu `--add-opens` đã được áp dụng cho đúng target, kết quả sẽ là `true`.

Có thể bổ sung thông tin layer và class loader:

~~~java
System.out.println("source layer = " + source.getLayer());
System.out.println("source loader = " + source.getClassLoader());
System.out.println("target layer = " + target.getLayer());
System.out.println("target loader = " + target.getClassLoader());
~~~

Layer và class loader hữu ích khi ứng dụng dùng plugin hoặc tạo nhiều module layer. Tên module đơn lẻ có thể chưa đủ để nhận diện module instance trong một tiến trình có nhiều layer.

## 7. Kiểm thử strong encapsulation của JDK

JPMS áp dụng ranh giới module cho các module nền tảng của JDK. Trên JDK hiện đại, nhiều package nội bộ không còn được mở rộng rãi cho reflection như một số ứng dụng cũ từng giả định.

Ví dụ thử truy cập private field `detailMessage` của `Throwable`:

~~~java
import java.lang.reflect.Field;

Field detailMessage =
        Throwable.class.getDeclaredField("detailMessage");

System.out.println(detailMessage.trySetAccessible());
~~~

Chạy probe trên class path mà không có JVM option mở package có thể cho kết quả `false`. Để thử nghiệm compatibility trong lab:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED --class-path probe-classes JdkReflectionProbe
~~~

Package `java.lang` thuộc module `java.base`; target là unnamed module của probe. Khi package được mở, `trySetAccessible()` có thể trả về `true`.

Đây chỉ là bài kiểm thử cơ chế. Không nên dựa vào private field hoặc JDK internal implementation như một API ứng dụng ổn định. Ưu tiên API công khai của JDK và framework. Trên JDK 17 trở lên, strong encapsulation của JDK internals được áp dụng mặc định; `--illegal-access` không khôi phục cơ chế truy cập rộng cũ.

## 8. Đặt option đúng trong Maven, Gradle và IDE

`--add-opens` là JVM option. Nó phải được truyền vào tiến trình Java thực hiện reflection, không phải argument của `main`.

### Maven Surefire

Nếu test chạy trong forked JVM, cấu hình option cho test process bằng `argLine`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--add-opens java.base/java.lang=ALL-UNNAMED --add-opens com.acme.domain/com.acme.domain.internal=ALL-UNNAMED</argLine>
    </configuration>
</plugin>
~~~

Đảm bảo forked test JVM có module domain trên module path và được resolve. Cấu hình module path phụ thuộc cách build/test project modular; chỉ thêm `argLine` không tự động đưa module domain vào graph.

### Gradle

Với test task sử dụng forked JVM:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
        "--add-opens=com.acme.domain/com.acme.domain.internal=ALL-UNNAMED"
    )
}
~~~

Nếu test chạy trong named test module, thay target `ALL-UNNAMED` bằng module name của test module khi phù hợp.

### IDE

Trong cấu hình Run/Debug, đặt option ở trường **VM options**:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Không đặt option vào **Program arguments**. Nếu framework chạy trong JVM do application server hoặc test runner tạo ra, phải cấu hình option ở đúng tiến trình đó. JVM của IDE hoặc build daemon không tự động truyền option sang mọi process con.

## 9. Xác nhận option đã được áp dụng

Khi nghi ngờ JVM option không được truyền tới đúng process, in input arguments từ trong chương trình:

~~~java
import java.lang.management.ManagementFactory;

ManagementFactory.getRuntimeMXBean()
        .getInputArguments()
        .forEach(System.out::println);
~~~

Kết quả nên chứa option `--add-opens` đã cấu hình. Cách này giúp phân biệt lỗi cấu hình launcher với lỗi chọn sai source package hoặc target module.

Có thể kiểm tra access bằng hai cách:

1. Gọi `trySetAccessible()` trên đúng member mà framework cần.
2. Gọi `Module.isOpen(packageName, targetModule)` trên module sở hữu package.

Nếu `isOpen` là `false`, kiểm tra lại source module, package spelling và target module. Nếu `isOpen` là `true` nhưng thao tác vẫn lỗi, xem lại member cụ thể, quyền truy cập Java thông thường, kiểu đối tượng hoặc lỗi khác trong framework.

## 10. Ma trận kiểm thử

| Source package | Target | JVM option | Kết quả mong đợi |
| --- | --- | --- | --- |
| `com.acme.domain.internal` | Unnamed module | Không có | `trySetAccessible()` trả về false |
| `com.acme.domain.internal` | Unnamed module | `--add-opens com.acme.domain/com.acme.domain.internal=ALL-UNNAMED` | Trả về true |
| `com.acme.domain.internal` | Named framework module | Mở cho `com.acme.framework` | Trả về true từ framework module |
| `com.acme.domain.internal` | Named framework module | Mở cho module khác | Không cấp quyền cho framework |
| `java.base/java.lang` | Unnamed module | Không có | Deep reflection bị chặn trên JDK hiện đại |
| `java.base/java.lang` | Unnamed module | `--add-opens java.base/java.lang=ALL-UNNAMED` | Reflection probe có thể truy cập member |

Với từng lần chạy, ghi lại JDK version, module path, root module, JVM arguments và output. Khi thử trường hợp target sai, giữ nguyên source module và probe, chỉ thay target để cô lập nguyên nhân.

## 11. Chẩn đoán lỗi thường gặp

### `InaccessibleObjectException`

Đọc phần `module ... does not "opens package" to ...`. Từ đó xác định source module, package và target module. Tạo option theo đúng mẫu:

~~~text
--add-opens source-module/package=target-module
~~~

### `trySetAccessible()` trả về false

Kiểm tra:

- Package có thuộc đúng source module không?
- Target có phải module chứa framework đang gọi không?
- Framework là named hay unnamed module?
- JVM option đã được truyền tới đúng process chưa?
- Test runner có fork một JVM khác không?

### `Module ... not found`

Đây là lỗi phân giải module, không phải lỗi deep reflection. Kiểm tra module path, module name và `--add-modules` hoặc root module được khởi chạy.

### `ClassNotFoundException`

Class cần kiểm tra chưa được tìm thấy bởi class loader đang dùng. Xác nhận module domain đã được resolve, class đã được biên dịch vào module output và tên đầy đủ của class chính xác.

### Option được in ra nhưng package vẫn đóng

Xác nhận option dùng đúng source module/package và target module. Một option mở `java.base/java.lang` không mở package `java.util`; mở cho `ALL-UNNAMED` cũng không mở cho named framework module.

## 12. Nguyên tắc sử dụng trong ứng dụng thật

- Chỉ mở package mà framework thực sự cần.
- Chọn named target module khi framework chạy trên module path.
- Dùng `ALL-UNNAMED` khi framework chạy trong unnamed module.
- Với module do bạn sở hữu, cân nhắc qualified `opens package to framework.module` trong `module-info.java`.
- Ghi lại lý do của mỗi JVM option và rà soát khi nâng cấp framework/JDK.
- Ưu tiên public API hoặc extension point của framework thay vì truy cập private implementation.
- Không dùng `--add-opens` để che giấu dependency hoặc access design sai ở các package không liên quan.

## Ghi nhớ

`--add-opens source-module/package=target-module` cấp quyền deep reflection cho đúng package và target. Bài lab chứng minh package nội bộ bị chặn khi chưa mở, rồi hoạt động khi mở cho `ALL-UNNAMED` hoặc named framework module phù hợp. `trySetAccessible()`, `InaccessibleObjectException` và `Module.isOpen(...)` cung cấp bằng chứng runtime. Hãy đặt option trong JVM arguments của đúng process và giữ phạm vi mở package ở mức tối thiểu.
