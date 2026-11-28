# Đóng gói mạnh của module và giới hạn truy cập phản chiếu

## 1. Tại sao Java cần đóng gói ở cấp module?

Từ khi Java Platform Module System (**JPMS**) được đưa vào Java 9, việc một lớp được khai báo **public** không còn có nghĩa rằng mọi module khác có thể truy cập lớp ấy. Java bổ sung **ranh giới module** bên cạnh mức truy cập **public**, **protected**, package-private và **private** vốn có.

Điều này giải quyết một vấn đề phổ biến trong các hệ thống lớn: thư viện có những lớp công khai về mặt cú pháp để các thành phần nội bộ dùng chung, nhưng không muốn biến mọi lớp đó thành API mà bên ngoài được phụ thuộc. Một module được quyền công bố **package nào là API**, package nào chỉ dùng trong nội bộ và package nào cho phép một framework truy cập bằng reflection.

Trong Java 27, **strong encapsulation** là mô hình hiện hành: một đoạn code ở module khác **không thể** tùy tiện mở thành viên private bằng **setAccessible(true)**. Việc vượt kiểm tra truy cập ngôn ngữ bằng reflection chỉ được phép nếu các điều kiện về module và package thỏa mãn.

Bài viết tập trung vào:

- **requires**, **exports**, **opens**, **opens ... to ...** và **open module**.
- Truy cập thông thường, reflection đến thành viên public và **deep reflection** đến private members.
- Sự khác nhau giữa **canAccess**, **trySetAccessible** và **setAccessible**.
- Những lỗi như **IllegalAccessException** và **InaccessibleObjectException**.
- Tùy chọn **--add-opens**, **--add-exports** và giới hạn của chúng.
- Cách thiết kế module rõ ràng, dùng reflection đúng phạm vi và tránh phụ thuộc vào JDK internals.

Các cơ chế được trình bày là API và quy tắc chuẩn của Java 27; các tùy chọn tương thích cũ đã mất hiệu lực sẽ chỉ được nhắc đến để **tránh sử dụng**, không được đề xuất làm giải pháp mới.

## 2. Một module là một ranh giới API

Một **named module** thường có tệp **module-info.java** khai báo tên module cùng những mối quan hệ cần thiết.

Ví dụ một thư viện:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Module này có thể chứa nhiều package:

~~~text
com.example.catalog
├── module-info.java
└── com/example/catalog/
    ├── api/
    │   └── CatalogService.java
    ├── internal/
    │   └── CatalogRepository.java
    └── model/
        └── CatalogRow.java
~~~

Ở đây chỉ package **com.example.catalog.api** được xuất công khai. Các package **internal** và **model** không phải API được công bố cho các module khác.

Để dùng API trong module **com.example.catalog**, một module phụ thuộc thường khai báo:

~~~java
module com.example.app {
    requires com.example.catalog;
}
~~~

Sau đó có thể import các kiểu **public** được xuất từ package **com.example.catalog.api**. Tuy nhiên, một khai báo **public class CatalogRepository** nằm trong package **internal** vẫn không tự trở thành kiểu được phép import từ module khác.

Điều kiện truy cập giữa hai named modules gồm nhiều yếu tố: module đích cần được **đọc** (*readability*) khi liên kết tên ở compile time, package phải được export đúng phạm vi và member phải có mức truy cập phù hợp.

~~~mermaid
flowchart LR
    A["com.example.app"] -->|"requires: reads"| B["com.example.catalog"]
    B -->|"exports"| C["catalog.api"]
    B -->|"không exports / opens"| D["catalog.internal"]
    A -->|"Dùng public API"| C
    A -.->|"Không tự truy cập được"| D
~~~

**Phân biệt:** **requires** giải quyết quan hệ phụ thuộc module; **exports** và **opens** giải quyết những quyền truy cập vào package của module đó. Chúng không thay thế lẫn nhau.

## 3. exports: công bố API cho code bên ngoài

Khai báo **exports package.name;** cho phép các module có quan hệ đọc thích hợp truy cập các **public types** và những members có thể truy cập theo quy tắc Java trong package đó.

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
}
~~~

Ví dụ:

~~~java
package com.example.catalog.api;

public record Product(String id, String name) {}
~~~

Module khác có thể import **Product**, tạo instance và gọi các accessor công khai của record. Điều này là truy cập thông thường, không cần reflection.

Tuy nhiên, **exports không đồng nghĩa mở toàn bộ members private**. Ví dụ:

~~~java
package com.example.catalog.api;

public final class ProductService {
    private final String internalState = "ready";

    public String status() {
        return "available";
    }
}
~~~

Với module khác:

- **new ProductService().status()** hợp lệ nếu module phụ thuộc được khai báo và package được export.
- Reflection có thể truy cập các thành viên **public** theo quy tắc thông thường.
- Chỉ vì package được **exports** không có nghĩa **setAccessible(true)** sẽ thành công trên field **internalState** từ module khác.

Cách thiết kế tốt là xuất **package API nhỏ** và giữ cấu trúc persistence, cache, implementation nội bộ ở package không export.

## 4. opens: cho phép phản chiếu sâu tại runtime

Một số framework cần phân tích metadata, gọi constructor không public hoặc truy cập field/private method để deserialize dữ liệu hay thực hiện dependency injection. Đó là **deep reflection**.

Khai báo:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
    opens com.example.catalog.internal;
}
~~~

**opens** cho phép các module khác phản chiếu sâu trên package được mở ở **runtime**, nếu những điều kiện liên quan được thỏa mãn.

Sự khác biệt quan trọng:

- **exports**: cho phép truy cập API public ở **compile time và runtime**, theo các mức truy cập ngôn ngữ.
- **opens**: cung cấp quyền truy cập phản chiếu ở **runtime**, bao gồm những members không public; **không** làm package trở thành package được import bình thường tại compile time.

Vì vậy, chỉ viết **opens com.example.catalog.internal;** không cho phép một module khác đặt:

~~~java
// Không hợp lệ chỉ nhờ opens ở module đích:
// import com.example.catalog.internal.InventoryRow;
~~~

Nếu cần import kiểu ở package đó như một API, phải xuất package bằng **exports** (và giữ mức truy cập ngôn ngữ phù hợp).

**Lưu ý an toàn thiết kế:** opens là một quyết định mở rộng quyền truy cập đáng kể. Chỉ nên mở package thực sự phải dùng reflection và chỉ cho module đáng tin cậy cần quyền đó.

## 5. Bảng so sánh requires, exports, opens

| Khai báo | Mục đích | Compile time | Runtime / reflection |
|---|---|---|---|
| **requires com.example.catalog;** | Module phụ thuộc đọc module catalog | Cho phép tham chiếu module, nhưng vẫn cần export | Xác lập quan hệ module; không tự mở private members |
| **exports p;** | Công bố package p như API | Public types của p khả dụng cho module đọc | Public members có thể truy cập; không tự cho deep reflection |
| **exports p to m;** | Công bố API của p chỉ cho module m | m được import public types | Chỉ phạm vi module được chỉ định |
| **opens p;** | Mở p cho deep reflection | Không tự cho import public types | Cho phép truy cập phản chiếu sâu từ các module khác |
| **opens p to m;** | Mở p cho module m | Không tự cho import | Chỉ module m được mở để deep reflection |
| **open module x { ... }** | Mở mọi package của x tại runtime | Chỉ các package được exports mới được import | Deep reflection được mở trên mọi package của module |

**Đọc đúng cột compile time:** Dù module đã **requires**, bên trong module đích vẫn cần **exports** để được sử dụng như public API tại thời điểm biên dịch. **opens** chủ yếu hỗ trợ reflection, không phải cơ chế thay thế requires/exports.

Trong một **open module**, mọi package đều được mở cho reflection theo đặc tả; khai báo **opens** riêng trong **open module** là không hợp lệ. Đây là lựa chọn phạm vi lớn, không nên dùng chỉ để giải quyết một trường hợp framework cần đọc một vài field.

## 6. Qualified exports và qualified opens

Để tuân thủ nguyên tắc cấp quyền tối thiểu, Java cho phép dùng **to** để hạn chế module nhận quyền:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;

    // Chỉ module mapper được phản chiếu sâu package model.
    opens com.example.catalog.model to com.example.mapper;
}
~~~

Một module khác như **com.example.reporting** không được quyền deep reflection vào **model** chỉ vì nó có **requires com.example.catalog**.

Nếu cần công bố một API cho vài module cụ thể:

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
    exports com.example.catalog.spi to
        com.example.mapper,
        com.example.reporting;

    opens com.example.catalog.model to com.example.mapper;
}
~~~

**Qualified export** và **qualified open** là hai cơ chế khác nhau. Một package có thể vừa export public API vừa mở reflection, nếu thực sự cần hai loại quyền; không nên tự động viết cả hai cho mọi package.

Tên sau **to** là **tên module**, không phải tên class, package hay tệp JAR. Khi dùng một thư viện, cần xác định **module name thực tế** của thư viện ở môi trường chạy. Không nên suy đoán tên module từ artifact filename trong mọi trường hợp.

## 7. Strong encapsulation không chỉ là từ khóa private

Mức truy cập **private** và package-private vẫn được áp dụng trong Java. JPMS thêm điều kiện ngoài cùng là **ranh giới module**.

Ví dụ một lớp public trong package không export:

~~~java
package com.example.catalog.internal;

public final class InventoryRow {
    private final String sku;

    public InventoryRow(String sku) {
        this.sku = sku;
    }
}
~~~

Dù class và constructor là **public**, code của module khác không thể import lớp này chỉ vì biết tên package của nó. Phương thức gọi bằng reflection cũng không tự có quyền tạo instance nếu package bị đóng.

Đổi **private** thành **public** trên field không giải quyết quyền truy cập package của module. Tương tự, thêm annotation lên field cũng không mở package.

Đây là điểm khác biệt lớn giữa việc **biết một tên class/member** và việc **được phép thao tác với class/member đó**.

## 8. Reflection: khám phá thành viên khác với truy cập thành viên

Java cung cấp reflection trong **java.lang.reflect**. Những API thường gặp:

| API | Công dụng |
|---|---|
| **Class.getFields()** | Lấy các field public, bao gồm field được kế thừa phù hợp |
| **Class.getDeclaredFields()** | Lấy field được khai báo trực tiếp, kể cả private |
| **Class.getMethods()** | Lấy các phương thức public phù hợp |
| **Class.getDeclaredMethods()** | Lấy phương thức được khai báo trực tiếp, kể cả private |
| **Class.getDeclaredConstructor(...)** | Tìm constructor khai báo trực tiếp có danh sách tham số phù hợp |
| **Field.get(...) / set(...)** | Đọc/ghi field khi quyền truy cập cho phép |
| **Method.invoke(...)** | Gọi phương thức khi quyền truy cập cho phép |
| **Constructor.newInstance(...)** | Tạo instance khi quyền truy cập cho phép |

Ví dụ:

~~~java
import java.lang.reflect.Field;

record Order(String id, int quantity) {}

for (Field field : Order.class.getDeclaredFields()) {
    System.out.println(field.getName());
}
~~~

Việc tìm thấy tên một field qua **getDeclaredFields()** không bảo đảm bạn được phép đọc hoặc sửa field đó từ module khác.

**Reflection metadata không đồng nghĩa với quyền can thiệp**. Điều kiện truy cập được kiểm tra khi thao tác, và trong một số trường hợp khi cố gắng yêu cầu bỏ qua kiểm tra truy cập.

Ngoài ra, thứ tự các phần tử trả về từ **getDeclaredFields()** không phải hợp đồng ổn định để làm thứ tự cột dữ liệu. Nếu serialization cần thứ tự chính xác, hãy định nghĩa quy tắc sắp xếp hoặc metadata vị trí riêng.

## 9. canAccess, trySetAccessible và setAccessible

Lớp **AccessibleObject** là nền tảng chung của **Field**, **Method** và **Constructor** trong reflection API. Ba thao tác cần phân biệt:

- **canAccess(target)**: kiểm tra member hiện có thể được sử dụng bởi caller với target phù hợp hay chưa.
- **trySetAccessible()**: cố cho phép bỏ qua một số kiểm tra truy cập. Trả **true** nếu thành công và **false** nếu không thể bật quyền theo ranh giới module.
- **setAccessible(true)**: cố bật quyền tương tự, nhưng có thể ném **InaccessibleObjectException** khi quyền module không cho phép.

~~~java
import java.lang.reflect.Field;

final class LocalExample {
    private String value = "demo";
}

LocalExample instance = new LocalExample();
Field field = LocalExample.class.getDeclaredField("value");

boolean before = field.canAccess(instance);
boolean enabled = field.trySetAccessible();
boolean after = field.canAccess(instance);

System.out.println("before=" + before);
System.out.println("enabled=" + enabled);
System.out.println("after=" + after);
~~~

Trong ví dụ cùng module, **trySetAccessible** thường bật được quyền cho member private. Trong một **named module khác**, nếu package đích không được mở phù hợp, kết quả có thể là **false**.

Không còn đúng khi nói “cứ gọi **setAccessible(true)** là truy cập được mọi private field”. Từ mô hình strong encapsulation, việc bật quyền chịu sự kiểm tra của ranh giới module.

**canAccess** không thay đổi quyền và yêu cầu target đúng: với instance field dùng một instance tương thích, còn với static field truyền **null**. Không nên dùng **AccessibleObject.isAccessible()** để thay cho **canAccess**: tên của phương thức cũ dễ gây hiểu nhầm về ý nghĩa cờ override.

## 10. InaccessibleObjectException và IllegalAccessException

Khi reflection không thể truy cập một member, các lỗi có thể xuất hiện ở những bước khác nhau:

~~~java
Field field = targetType.getDeclaredField("value");

// Nếu không được mở:
// field.setAccessible(true)
//   -> có thể ném InaccessibleObjectException.

// Nếu không bật truy cập mà vẫn cố đọc:
// field.get(target)
//   -> có thể ném IllegalAccessException.
~~~

| Lỗi / tình huống | Thời điểm thường gặp | Nguyên nhân |
|---|---|---|
| **InaccessibleObjectException** | **setAccessible(true)** | Module/package không cho phép mở quyền reflection tương ứng |
| **trySetAccessible() == false** | Khi thử bật truy cập | Không thể mở quyền theo các điều kiện của module |
| **IllegalAccessException** | **Field.get**, **Method.invoke**, **Constructor.newInstance** | Quyền truy cập đang áp dụng không cho phép thao tác |
| **NoSuchFieldException** | **getDeclaredField** | Member không có tên/chữ ký mong đợi trong lớp đã cho |
| **NoSuchMethodException** | Tìm method/constructor | Không có member với chữ ký được yêu cầu |
| **InvocationTargetException** | **Method.invoke/Constructor.newInstance** | Code được gọi tự ném exception và lỗi được bọc khi phản chiếu |

**Không sửa mọi lỗi reflection bằng cách thêm --add-opens một cách tự động.** Có thể sai tên field, sai constructor signature, loại đối tượng không phù hợp, thư viện không tương thích hoặc một lỗi nghiệp vụ bên trong phương thức được gọi.

Khi log lỗi phản chiếu, hãy giữ **cause** khi bọc exception, phân biệt lỗi truy cập với lỗi xảy ra trong logic được gọi và không để lộ cấu trúc nội bộ nhạy cảm trong response công khai.

## 11. Ví dụ hoàn chỉnh: hai named modules

Ví dụ này cho thấy một module công bố annotation API nhưng chỉ cho một module tin cậy đọc private field của kiểu nội bộ qua reflection. Tất cả ví dụ dùng API Java chính thức, không dùng preview.

Cấu trúc thư mục minh họa:

~~~text
src/
├── com.acme.catalog/
│   ├── module-info.java
│   └── com/acme/catalog/
│       ├── api/Column.java
│       └── internal/InventoryRow.java
└── com.acme.inspector/
    ├── module-info.java
    └── com/acme/inspector/Main.java
~~~

**Tệp src/com.acme.catalog/module-info.java:**

~~~java
module com.acme.catalog {
    exports com.acme.catalog.api;
    opens com.acme.catalog.internal to com.acme.inspector;
}
~~~

**Tệp src/com.acme.catalog/com/acme/catalog/api/Column.java:**

~~~java
package com.acme.catalog.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
public @interface Column {
    String value();
}
~~~

**Tệp src/com.acme.catalog/com/acme/catalog/internal/InventoryRow.java:**

~~~java
package com.acme.catalog.internal;

import com.acme.catalog.api.Column;

public final class InventoryRow {
    @Column("sku")
    private final String sku;

    public InventoryRow(String sku) {
        this.sku = sku;
    }
}
~~~

**Tệp src/com.acme.inspector/module-info.java:**

~~~java
module com.acme.inspector {
    requires com.acme.catalog;
}
~~~

**Tệp src/com.acme.inspector/com/acme/inspector/Main.java:**

~~~java
package com.acme.inspector;

import com.acme.catalog.api.Column;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<?> type = Class.forName(
            "com.acme.catalog.internal.InventoryRow"
        );

        var constructor = type.getDeclaredConstructor(String.class);
        if (!constructor.trySetAccessible()) {
            throw new IllegalStateException(
                "Catalog did not open its internal package"
            );
        }

        Object row = constructor.newInstance("JAVA-27");

        for (Field field : type.getDeclaredFields()) {
            Column column = field.getAnnotation(Column.class);
            if (column == null) {
                continue;
            }

            if (!field.trySetAccessible()) {
                throw new IllegalStateException(
                    "Cannot access mapped field: " + field.getName()
                );
            }

            System.out.println(
                column.value() + "=" + field.get(row)
            );
        }
    }
}
~~~

**Điểm đặc biệt của ví dụ:**

1. **Column** nằm trong package **api** được **exports**, do đó module inspector có thể import annotation.
2. **InventoryRow** nằm trong package **internal**, **không exports**, nên inspector không import nó trực tiếp.
3. Inspector chỉ biết tên InventoryRow tại runtime qua **Class.forName**; điều đó **không tự cấp quyền** truy cập member.
4. **opens ... to com.acme.inspector** cho phép inspector dùng reflection vào constructor và field của kiểu nội bộ.
5. **@Retention(RUNTIME)** giữ annotation trong metadata runtime để **getAnnotation** có thể nhìn thấy. Annotation này **không cấp quyền** truy cập field; quyền đến từ module opening.

Trong ứng dụng thật, hãy ưu tiên dữ liệu demo hoặc metadata không nhạy cảm. Quyền reflection vào private fields phải là thỏa thuận kiến trúc giữa module dữ liệu và module xử lý; không dùng nó để truy xuất bí mật của thành phần không đồng ý mở quyền.

## 12. Biên dịch và chạy hai module

Từ thư mục chứa **src**, sử dụng JDK 27:

~~~bash
javac --module-source-path src -d mods --module com.acme.catalog,com.acme.inspector
java --module-path mods --module com.acme.inspector/com.acme.inspector.Main
~~~

Kết quả dự kiến:

~~~text
sku=JAVA-27
~~~

Lệnh javac biên dịch các named modules từ cây **src**, còn java chạy main class của module inspector qua module path. Không cần chỉnh classpath hoặc tắt cơ chế đóng gói.

**Thử nghiệm để quan sát giới hạn:**

1. Xóa dòng **opens com.acme.catalog.internal to com.acme.inspector;** trong module catalog.
2. Biên dịch lại hai module như trên.
3. Chạy lại inspector.

Lần này **constructor.trySetAccessible()** sẽ trả **false** theo quy tắc module access, và ví dụ ném **IllegalStateException** với thông điệp do chính ứng dụng đưa ra.

Nếu đổi **trySetAccessible()** thành **setAccessible(true)** trong tình huống package không mở, lời gọi bật quyền có thể ném **InaccessibleObjectException**.

**Cần phân biệt:** Đây là ví dụ cho **cơ chế module do chính ứng dụng sở hữu**, không phải hướng dẫn can thiệp vào private fields của các thư viện hoặc JDK mà bạn không kiểm soát.

## 13. Tạo public API thay vì mở private field

Mặc dù có thể mở package cho framework, mã nghiệp vụ bình thường nên làm việc qua **public API** của module.

Ví dụ, catalog có thể công bố một record DTO:

~~~java
package com.acme.catalog.api;

public record InventoryView(String sku) {}
~~~

Một service trong package API có thể chuyển đổi từ kiểu nội bộ thành DTO rồi trả ra cho caller. Cách làm này mang lại lợi ích:

- Bên gọi không phụ thuộc tên hoặc cấu trúc field private.
- Module được quyền sửa implementation mà không làm hỏng bên ngoài.
- Không cần **opens** cho những caller chỉ cần đọc dữ liệu theo hợp đồng.
- DTO/record công khai định nghĩa rõ phần dữ liệu được phép lộ.

Reflection có giá trị cho framework, serializer hoặc công cụ phân tích metadata; nhưng không phải lựa chọn mặc định cho giao tiếp nghiệp vụ giữa các module.

## 14. Khi nào cần kết hợp exports và opens?

Một framework có thể yêu cầu đọc metadata của DTO public nhưng cũng cần gọi constructor/field không public. Khi đó package có thể vừa xuất API vừa mở reflection.

~~~java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.api to com.example.mapper;
}
~~~

Ở ví dụ này:

- Các module có quan hệ đọc thích hợp có thể sử dụng public types từ **orders.api**.
- Module **com.example.mapper** còn được cho phép deep reflection trên package đó.
- Các module khác không tự có quyền deep reflection vào private members chỉ vì package đã exports.

Không áp dụng mẫu này cho mọi package. Nhiều framework xử lý được qua constructor hoặc accessor public, không cần truy cập private fields. Nên kiểm tra nhu cầu thực tế của phiên bản framework đang sử dụng rồi **mở ít nhất có thể**.

## 15. Dùng MethodHandles đúng theo module boundaries

Ngoài **java.lang.reflect**, Java có **java.lang.invoke.MethodHandles** cho quyền truy cập động được kiểm tra qua **Lookup**.

Một đoạn mã minh họa (giả sử biến **type** là Class của InventoryRow và **row** là instance, như trong ví dụ hai module):

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.privateLookupIn(
    type,
    MethodHandles.lookup()
);

MethodHandle getter = lookup.findGetter(
    type,
    "sku",
    String.class
);

String sku = (String) getter.invoke(row);
System.out.println(sku);
~~~

Đoạn code này cần xử lý **Throwable** theo chữ ký của **MethodHandle.invoke**. Quan trọng hơn, **privateLookupIn** không phải đường vòng để phá đóng gói. Với target ở module khác, nó cần các điều kiện module phù hợp, bao gồm **readability** và package đích được **opens** cho module caller.

Nên dùng MethodHandles khi có lý do kiến trúc hoặc hiệu năng đã xác định. Còn với API thông thường, một constructor public hoặc phương thức public rõ ràng vẫn dễ bảo trì và dễ kiểm thử hơn.

**Không cố sửa final fields bằng reflection hoặc MethodHandles.** Có quyền nhìn thấy field không đồng nghĩa được phép thay đổi mọi bất biến ngôn ngữ. Java có các hạn chế đối với final fields, đặc biệt với record và những kiểu mà bất biến phải được giữ từ thời điểm tạo object.

## 16. Truy vấn module ở runtime bằng Module API

Có thể kiểm tra quan hệ module thực tế khi chẩn đoán vấn đề:

~~~java
Module catalogModule = type.getModule();
Module inspectorModule = Main.class.getModule();

String packageName = "com.acme.catalog.internal";

System.out.println(catalogModule.getName());
// com.acme.catalog

System.out.println(inspectorModule.getName());
// com.acme.inspector

System.out.println(
    catalogModule.isOpen(packageName, inspectorModule)
); // true nếu qualified opens được khai báo như ví dụ
~~~

Các phương thức hữu ích:

- **Module.getName()**: tên module, hoặc null cho unnamed module.
- **Module.isNamed()**: module có tên hay không.
- **Module.canRead(other)**: quan hệ đọc ở runtime.
- **Module.isExported(packageName, other)**: export có hiệu lực với module other ở runtime.
- **Module.isOpen(packageName, other)**: package có mở cho reflection đối với module other hay không.

**Lưu ý:** Theo Module API, một package được **opens** cho module khác cũng được xem như **exported ở runtime** đối với module đó để phục vụ quyền truy cập runtime. Vì vậy, không nên dùng riêng **isExported(packageName, other)** để suy ra rằng package đã được công bố thành API tại compile time. Muốn xác định API được thiết kế để dùng từ source, hãy xem khai báo module và tài liệu công khai tương ứng.

Phân biệt **Module** là đối tượng runtime và **ModuleDescriptor** mô tả module; các phép truy vấn runtime phản ánh cấu hình được áp dụng, có thể bao gồm những thay đổi qua command-line options.

## 17. Thêm quyền truy cập khi chạy bằng --add-opens

Trong một số tình huống chuyển đổi hệ thống, module không thể sửa khai báo module-info.java ngay nhưng framework cũ cần reflection vào một package cụ thể. Java launcher hỗ trợ:

~~~text
--add-opens=<source-module>/<package>=<target-module>
~~~

Ví dụ với module ở bài:

~~~bash
java --module-path mods --add-opens=com.acme.catalog/com.acme.catalog.internal=com.acme.inspector --module com.acme.inspector/com.acme.inspector.Main
~~~

Cách dùng này hữu ích khi **đã bỏ dòng opens** trong module-info của catalog nhưng vẫn muốn thử quyền mở package cho inspector tại runtime. Tùy chọn **--add-opens** không yêu cầu biến mọi package của catalog thành open.

Nếu caller chạy từ classpath và thuộc unnamed module, cú pháp target đặc biệt là:

~~~text
--add-opens=<source-module>/<package>=ALL-UNNAMED
~~~

**Đây là quyền mở rộng cho tất cả unnamed modules**, không chỉ một class riêng. Vì vậy, nên ưu tiên named module và qualified opens khi có thể, nhất là trong deployment production.

Các cờ dòng lệnh là công cụ cấu hình hoặc chuyển đổi có chủ ý, **không nên là giải pháp mặc định để né thiết kế API**. Hãy ghi rõ module/package nào được mở, ai cần nó, lý do và kế hoạch thu hẹp quyền về sau.

## 18. --add-exports không đồng nghĩa --add-opens

Java launcher và compiler hỗ trợ **--add-exports** để công bố thêm một package cho những module được chỉ định, có ích khi code đã cần dùng public types từ package chưa được exports.

~~~text
--add-exports=<source-module>/<package>=<target-module>
~~~

Khác biệt:

| Cờ | Cho phép điều gì? | Không tự cho phép điều gì? |
|---|---|---|
| **--add-exports** | Truy cập public types/public members của package theo quy tắc export; có thể dùng trong cấu hình compile/run phù hợp | Không tự cho reflection vào private members |
| **--add-opens** | Cho phép deep reflection vào package ở runtime cho các module đích | Không tự cho source code import package tại compile time |

Ví dụ một thành phần có thể import được kiểu public từ package đã bổ sung export, nhưng việc gọi **setAccessible(true)** trên field private vẫn có thể bị chặn nếu package chưa được mở thích hợp.

Đừng đặt **--add-opens** vào lệnh javac rồi giả định nó thay thế quyền biên dịch. Khi cần tạm cho mã nguồn tham chiếu public types qua ranh giới module, dùng cơ chế **--add-exports** ở cấu hình biên dịch thích hợp, đồng thời xem xét hệ quả ở runtime.

**Thiết kế mới nên công bố API bằng exports**; các cờ trên chỉ nên dùng khi có nhu cầu triển khai thực tế và đã hiểu phạm vi quyền.

## 19. Tại sao --illegal-access không còn là giải pháp?

Trong quá trình chuyển đổi sau Java 9, một số ứng dụng từng dựa vào cơ chế nới lỏng phản chiếu trên JDK internals. Tuy nhiên, chính sách đó đã thay đổi.

**JEP 403** đưa strong encapsulation đối với phần lớn JDK internals vào mô hình mặc định của Java 17 trở lên. Tùy chọn **--illegal-access** vốn dùng cho tương thích giai đoạn chuyển tiếp đã **lỗi thời và không còn hiệu lực mở truy cập** trong Java 17 trở lên.

Vì vậy, với Java 27:

- Không hướng dẫn người học dùng **--illegal-access=permit** như cách sửa lỗi reflection.
- Không coi private fields trong **java.base** hoặc implementation classes của JDK là API ổn định.
- Ưu tiên API công khai, cập nhật phiên bản framework/library và cấu hình module được tài liệu hóa.
- Nếu chưa thể nâng cấp một thư viện, **--add-opens** có phạm vi hẹp có thể là biện pháp chuyển tiếp, nhưng phải hiểu rõ tác động và mục tiêu loại bỏ phụ thuộc nội bộ.

Các API nội bộ có thể thay đổi mà không giữ cam kết tương thích như API công khai. Khả năng truy cập tại một phiên bản không bảo đảm sẽ giữ nguyên ở các phiên bản sau.

## 20. Classpath, unnamed modules và automatic modules

Ứng dụng Java vẫn có thể dùng classpath. Các lớp trên classpath thuộc về **unnamed module** tương ứng với class loader. Theo quy tắc module system, unnamed modules có cách xử lý rộng hơn đối với những package do chính chúng chứa, bao gồm export/open các package đó.

Điều này giải thích vì sao một thư viện cũ chạy trên classpath có thể cho phép deep reflection đến những lớp của nó nhưng khi chuyển thành **named module**, cùng code gặp lỗi không mở package.

Tuy nhiên, **unnamed module không được quyền tự mở private members của named module khác**. Ví dụ một thư viện trên classpath không thể mặc nhiên dùng **setAccessible(true)** để truy cập private field của một JDK module bị đóng.

**Automatic module** là một module có tên được tạo ra khi đặt một JAR chưa có module descriptor lên module path. Nó có cơ chế chuyển đổi phù hợp cho tính tương thích, bao gồm việc các package của automatic module được export/open rộng hơn so với named module được khai báo tường minh. Đây không phải lý do để chủ động bỏ qua thiết kế descriptor lâu dài cho thư viện của mình.

Khi chẩn đoán lỗi, hãy xác định:

1. Code chạy từ classpath hay module path?
2. Caller và target là named, automatic hay unnamed module?
3. Target package có được exports/opens đúng module đích không?
4. Cấu hình JVM có thêm --add-opens hoặc --add-exports không?

Cùng một JAR có thể thể hiện hành vi khác nhau tùy cách đóng gói và nạp module, nên cần kiểm thử đúng mô hình triển khai thực tế.

## 21. Annotation không tự cấp quyền reflection

Một annotation có runtime retention cho phép framework **nhìn thấy metadata**, nhưng **không cấp quyền truy cập private members**.

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface MappedField {
    String value();
}

final class UserRecord {
    @MappedField("user_id")
    private final String id;

    UserRecord(String id) {
        this.id = id;
    }
}
~~~

Một scanner có thể tìm field được đánh dấu bằng **@MappedField**:

~~~java
for (var field : UserRecord.class.getDeclaredFields()) {
    MappedField metadata = field.getAnnotation(MappedField.class);
    if (metadata != null) {
        System.out.println(metadata.value());
    }
}
~~~

Nhưng để đọc giá trị **id** từ code ở module khác, cần xét **trySetAccessible** và xem package có được **opens** cho module scanner hay không.

Đó là lý do một framework có thể báo **InaccessibleObjectException** dù annotation vẫn được tìm thấy: tìm annotation và lấy giá trị private field là **hai hành động có quy tắc quyền khác nhau**.

Annotation processing tại compile time cũng là một khái niệm khác với reflection tại runtime. Một annotation processor chạy trong quá trình biên dịch không đương nhiên nhận quyền reflective access vào toàn bộ runtime modules.

## 22. Framework serialization, ORM và dependency injection

Những framework có thể sử dụng reflection bao gồm:

- JSON/XML serializer/deserializer khi cần tạo object hoặc đọc field không public.
- ORM khi ánh xạ entity field hoặc constructor đặc biệt.
- Dependency injection container khi dựng component, gán field hoặc gọi callback.
- Test framework, công cụ tạo mock và plugin discovery.

Tuy nhiên, **không phải mọi framework hoặc mọi class đều cần opens**. Một số thư viện dùng public constructor/getters, annotation processing, generated code hoặc MethodHandles với quyền phù hợp; điều kiện chính xác phụ thuộc bản phát hành và chế độ cấu hình.

Cách xử lý có hệ thống:

1. Đọc thông báo lỗi đầy đủ để xác định **module nguồn**, **package** và **module caller**.
2. Kiểm tra library/framework đã hỗ trợ JPMS và Java 27 hay chưa.
3. Ưu tiên nâng cấp thư viện và dùng API công khai/constructor phù hợp.
4. Nếu thực sự cần private reflection, cân nhắc **qualified opens** vào đúng module của framework.
5. Chỉ dùng **--add-opens** ở runtime khi có lý do rõ ràng, phạm vi giới hạn và được kiểm thử.
6. Không thêm **open module** cho toàn bộ ứng dụng chỉ vì một serializer cần truy cập một package.

Nhớ rằng module name của thư viện không nhất thiết bằng Maven groupId/artifactId. Hãy xác minh tên module thực tế bằng công cụ module hoặc tài liệu của thư viện trước khi ghi **opens ... to ...**.

## 23. Kiểm tra dependency và module path

Một số công cụ JDK giúp kiểm tra module:

~~~bash
java --list-modules
java --describe-module java.base
jdeps --module-path mods --module com.acme.inspector
~~~

Các tác vụ có ý nghĩa:

- **--list-modules**: liệt kê các module hệ thống được runtime quan sát.
- **--describe-module**: xem thông tin mô tả của module.
- **jdeps**: phân tích sự phụ thuộc package/class/module của artifact, hữu ích khi lập kế hoạch chuyển đổi sang JPMS.

Phân tích tĩnh không thể luôn tìm ra mọi reflective access thực tế vì tên class/member có thể được tạo từ cấu hình hoặc chuỗi ở runtime. Vì vậy cần kiểm thử tích hợp theo cấu hình triển khai thật, bao gồm module path, các cờ JVM và framework cụ thể.

Không lạm dụng các công cụ build để cấp quyền rộng chỉ nhằm che lỗi. Mỗi override nên có lý do và phạm vi được ghi nhận trong cấu hình triển khai.

## 24. Ranh giới module không phải sandbox bảo mật

**Strong encapsulation** giúp bảo vệ hợp đồng module và ngăn phụ thuộc tùy tiện vào members nội bộ. Nhưng JPMS **không phải sandbox bảo mật** để chạy mã không tin cậy.

Đừng hiểu rằng chỉ cần không exports/opens là một plugin độc hại không thể thực hiện bất kỳ hành động nguy hiểm nào. Quyền hệ điều hành, dữ liệu bí mật, quyền truy cập mạng/file, kiểm soát dependency và cơ chế cô lập tiến trình là những vấn đề bảo mật khác cần giải pháp riêng.

Ngược lại, **opens** cấp quyền phản chiếu sâu đáng kể cho những module đích được phép; hãy coi đó là một hợp đồng tin cậy, không chỉ là cờ để “hết báo lỗi”. Đặc biệt không nên mở rộng toàn bộ các package chứa credential, khóa bí mật hoặc cấu trúc nhạy cảm cho các module không được kiểm soát.

Giữ ranh giới module tối thiểu vẫn có giá trị ngay cả khi mã của ứng dụng được tin cậy: nó giảm coupling, giúp nâng cấp thư viện và làm rõ kiến trúc hệ thống.

## 25. Phát hiện và xử lý lỗi trong môi trường production

Khi xuất hiện lỗi reflective access, hãy điều tra từng bước:

| Dấu hiệu | Câu hỏi cần đặt ra | Hướng giải quyết |
|---|---|---|
| **package is not visible** lúc biên dịch | Module đã requires và package đã exports chưa? | Chỉnh descriptor, dùng API công khai |
| **IllegalAccessException** khi invoke/get | Member có public? Package export/open phù hợp? | Dùng accessor công khai hoặc mở đúng package |
| **InaccessibleObjectException** khi setAccessible | Package đích có opens cho caller module? | Qualified opens nếu được phép |
| **trySetAccessible() == false** | Caller có được cấp quyền deep reflection không? | Không cố ép; chỉnh kiến trúc hoặc descriptor |
| Class được tìm thấy nhưng không tạo instance được | Constructor, package và quyền reflection? | Dùng factory/constructor public hoặc mở có chủ ý |
| ClassNotFoundException | Class có trên module path/classpath và được resolve không? | Kiểm tra đóng gói và cách nạp lớp |
| NoSuchFieldException / NoSuchMethodException | Tên/chữ ký có thay đổi? | Cập nhật reflection metadata, tránh phụ thuộc nội bộ |
| Module lỗi chỉ ở production | Khác JDK, module path hoặc JVM options? | Đối chiếu đúng command line và bản dependency |
| Framework đọc annotation nhưng không đọc private field | Retention không cấp quyền truy cập | Dùng opens cho module thật sự cần, hoặc API public |

**Không bắt Exception rồi bỏ qua để coi deserialize thành công.** Nếu dữ liệu không được ánh xạ đầy đủ, ứng dụng có thể tạo một object sai bất biến và phát sinh lỗi ở vị trí xa nguyên nhân gốc.

Việc bọc exception ở ranh giới có thể dùng để thêm ngữ cảnh, nhưng nên giữ **cause** cho chẩn đoán và không trả thông tin đường dẫn/internal package lên API client công khai.

## 26. Bài tập thực hành

**Bài tập 1 — exports và private field.** Tạo một named module có package public API chứa class public với private field. Từ module khác, gọi public method thành công; thử gọi **setAccessible(true)** trên private field và giải thích vì sao exports không đủ.

**Bài tập 2 — qualified opens.** Dùng ví dụ hai module trong bài, chạy khi có và khi không có **opens ... to ...**. So sánh **trySetAccessible()**, **setAccessible(true)** và **canAccess(instance)**.

**Bài tập 3 — command-line override.** Bỏ khai báo opens trong module catalog, chạy cùng chương trình bằng **--add-opens=com.acme.catalog/com.acme.catalog.internal=com.acme.inspector**. Giải thích vì sao kết quả khác trước khi thêm cờ.

**Bài tập 4 — public API thay reflection.** Tạo record DTO trong package được exports và một public service trả DTO. Viết lại module inspector để không dùng **getDeclaredFields** hoặc **setAccessible**.

**Bài tập 5 — annotation và quyền.** Định nghĩa annotation với **RetentionPolicy.RUNTIME**, gắn lên private field rồi viết scanner. Kiểm tra rằng nhìn thấy annotation không đồng nghĩa đọc được field nếu package đích chưa mở.

**Bài tập 6 — classpath vs module path.** So sánh hành vi của thư viện chỉ đặt trên classpath với named module có module-info. Nêu rõ module nào là target, module nào là caller và kết quả của **isOpen**.

**Bài tập 7 — ghi nhận rủi ro kiến trúc.** Xem một cấu hình ứng dụng có nhiều cờ **--add-opens**. Phân nhóm cờ theo dependency, module/package đích, phiên bản thư viện và giải pháp thay thế; đề xuất kế hoạch thu hẹp quyền.

## 27. Checklist thiết kế module và reflection trên Java 27

- [ ] Phân biệt **module readability**, **package exports**, **package opens** và mức truy cập thành viên.
- [ ] Xác định package nào là public API; chỉ **exports** các package đó.
- [ ] Giữ các package implementation không export trừ khi có hợp đồng rõ ràng.
- [ ] Chỉ **opens** package thật sự cần deep reflection.
- [ ] Ưu tiên **opens ... to module** thay vì mở rộng cho mọi module.
- [ ] Không hiểu **opens** là quyền import source ở compile time.
- [ ] Không hiểu **exports** là quyền truy cập mọi private members.
- [ ] Kiểm tra **trySetAccessible** và xử lý trường hợp false thay vì giả định bật quyền luôn thành công.
- [ ] Phân biệt **IllegalAccessException**, **InaccessibleObjectException**, lỗi tìm member và lỗi được invoke ném ra.
- [ ] Nhớ rằng **@Retention(RUNTIME)** không cấp quyền reflection.
- [ ] Xác định đúng module name thực tế của framework và vị trí classpath/module path.
- [ ] Tránh tạo **open module** chỉ để sửa một lỗi serializer đơn lẻ.
- [ ] Không dùng **--illegal-access** như giải pháp Java 27.
- [ ] Chỉ dùng **--add-opens** hoặc **--add-exports** khi thật sự cần, ghi lại lý do và phạm vi.
- [ ] Ưu tiên API public, public factory/constructor hoặc DTO thay vì private reflection trong mã nghiệp vụ.
- [ ] Không dựa vào private implementation của JDK như hợp đồng API.
- [ ] Kiểm thử tích hợp trên cấu hình JVM, JDK và module path tương ứng production.
- [ ] Không xem JPMS là sandbox bảo mật cho mã không tin cậy.
- [ ] Đảm bảo việc mở quyền không vô tình làm lộ dữ liệu nhạy cảm.
- [ ] Ghi nhận mọi ngoại lệ chuyển đổi có nguyên nhân rõ, không che giấu lỗi reflective access.

**Kết luận:** Strong encapsulation trong Java 27 là cơ chế thiết kế ranh giới module có ý nghĩa thực tế. **exports** công bố public API; **opens** cấp quyền reflection ở runtime; **requires** mô tả quan hệ phụ thuộc module. Khi hiểu sự khác biệt giữa các cơ chế này và các giới hạn của **setAccessible**, **trySetAccessible** và MethodHandles, lập trình viên có thể xây dựng các module dễ bảo trì, tích hợp framework có kiểm soát và tránh phụ thuộc vào chi tiết nội bộ của JDK.

## Tài liệu tham khảo

- [Java Language Specification 27 — §7.7 Module Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-7.html#jls-7.7): định nghĩa normal/open modules, requires, exports và opens.
- [Java SE 27 — AccessibleObject](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html): canAccess, trySetAccessible, setAccessible và điều kiện truy cập qua module.
- [Java SE 27 — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): exception khi không thể bật quyền truy cập phản chiếu.
- [Java SE 27 — Module](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Module.html): canRead, isExported, isOpen và metadata runtime.
- [Java SE 27 — ModuleDescriptor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/module/ModuleDescriptor.html): descriptor của named, automatic và open module.
- [Java SE 27 — MethodHandles](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.html): lookup và privateLookupIn.
- [Oracle JDK 27 Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): strong encapsulation và --add-opens/--add-exports.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): lý do loại bỏ khả năng truy cập tùy tiện JDK internals.
