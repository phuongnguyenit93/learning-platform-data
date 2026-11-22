# Reflection trong ORM, serializer, proxy và thư viện kiểm thử

Trong một dự án **Java Advance Compatibility Migration**, reflection thường là nguyên nhân của các lỗi chỉ xuất hiện ở runtime. Mã nguồn ứng dụng vẫn biên dịch được, nhưng khi ORM dựng entity, serializer đọc một trường riêng tư, framework tạo proxy hoặc thư viện kiểm thử khởi tạo mock, chương trình có thể gặp lỗi truy cập, lỗi nạp lớp hoặc lỗi instrument bytecode.

Đây là nội dung thuộc chương **Reflection và API nội bộ**. Mục tiêu không chỉ là biết cách gọi **Class.getDeclaredField()** hay **Method.invoke()**, mà còn hiểu vì sao các thư viện hoạt động được trên một JDK nhưng thất bại trên JDK khác, cách phân biệt lỗi do Java Platform Module System (JPMS) với lỗi do framework/dependency, và cách kiểm chứng tương thích sau migration.

Các ví dụ sử dụng API Java chuẩn và cấu hình minh họa. Tên module thực tế của Hibernate, Jackson, Mockito, Byte Buddy hoặc ứng dụng phải được xác nhận từ artifact và module graph đang chạy; không sao chép máy móc các tên module ví dụ vào production.

## 1. Vì sao reflection là một vùng rủi ro khi nâng cấp Java?

Reflection cho phép chương trình khám phá và thao tác cấu trúc lớp tại runtime: tên kiểu, constructor, field, method, annotation và đôi khi cả các thành viên không public. Framework dùng khả năng này để xử lý lớp mà nó không biết cụ thể tại thời điểm biên dịch.

Ví dụ:

- **ORM:** đọc annotation, tạo entity, gán khóa chính hoặc hydrate dữ liệu từ kết quả truy vấn.
- **Serializer:** xác định property và constructor, chuyển đối tượng thành JSON/XML rồi dựng lại đối tượng.
- **Proxy/AOP:** khám phá method, tạo lớp trung gian, ủy quyền lời gọi hoặc chèn logic giao dịch/logging.
- **Thư viện kiểm thử:** tìm method có annotation, chạy test, tạo mock, inject dependency hoặc thay đổi hành vi method.

Các cơ chế này thường phụ thuộc vào chi tiết mà một API thông thường không cần: visibility, constructor không tham số, package, class loader, tên tham số, annotation retention, final/sealed modifier và khả năng mở package cho deep reflection.

Một thay đổi có vẻ nhỏ như chuyển một thư viện từ classpath sang module path, cập nhật JDK hoặc đổi implementation của mock maker có thể làm thay đổi các quy tắc runtime.

### 1.1. Đừng đánh đồng bốn khái niệm tương thích

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| Source compatibility | Source hiện có còn biên dịch được không? | Import API cũ bị xóa |
| Binary compatibility | Bytecode đã biên dịch còn liên kết được không? | NoSuchMethodError, IllegalAccessError |
| Reflective compatibility | Framework còn tìm và truy cập đúng thành viên ở runtime không? | InaccessibleObjectException, NoSuchMethodException |
| Behavioral compatibility | Kết quả nghiệp vụ còn đúng không? | JSON đổi tên trường, proxy không áp dụng advice |

Một bản build xanh không chứng minh ba khía cạnh còn lại. Reflection thường diễn ra muộn: lần truy vấn đầu tiên, khi nhận payload đặc biệt, khi nạp plugin hoặc khi một test suite riêng được chạy.

### 1.2. Phân biệt API công khai với chi tiết triển khai

Nếu một thư viện chỉ gọi method public qua kiểu được export, nó ít phụ thuộc vào cấu trúc riêng tư hơn so với việc tìm field private bằng tên chuỗi. Deep reflection thường là một phụ thuộc ngầm vào implementation.

Ví dụ, **Customer.id** có thể không xuất hiện trong Java API công khai, nhưng mapper vẫn dựa vào đúng tên và kiểu của trường này. Đổi tên field có thể không gây lỗi compile ở consumer nhưng làm thay đổi mapping, dữ liệu hoặc hành vi serialization.

## 2. Nền tảng Reflection API

Java Reflection API nằm chủ yếu trong **java.lang.Class**, **java.lang.reflect** và các API liên quan.

### 2.1. Khám phá field, method và constructor

~~~java
package example;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public final class InspectPerson {
    public static void main(String[] args) {
        Class<Person> type = Person.class;

        for (Field field : type.getDeclaredFields()) {
            System.out.println("field: " + field.getName());
        }

        for (Method method : type.getDeclaredMethods()) {
            System.out.println("method: " + method.getName());
        }

        for (Constructor<?> constructor : type.getDeclaredConstructors()) {
            System.out.println("constructor: " + constructor);
        }
    }

    static class Person {
        private String name;

        private Person(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }
}
~~~

**getDeclaredFields()** trả về các field được khai báo trực tiếp trong class, gồm cả private, nhưng không tự động trả về field kế thừa. **getFields()** tập trung vào các field public có thể truy cập qua class, gồm các thành viên public được kế thừa.

Tương tự, **getDeclaredMethods()** và **getMethods()** khác nhau về phạm vi thành viên. Khi migration, sự khác biệt này quan trọng: một framework thay đổi chiến lược quét từ public accessor sang declared field có thể gặp ràng buộc truy cập mới.

### 2.2. Truy cập private member

~~~java
package example;

import java.lang.reflect.Field;

public final class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        Account account = new Account("A-001");

        Field field = Account.class.getDeclaredField("id");
        field.setAccessible(true);

        String id = (String) field.get(account);
        System.out.println(id);
    }

    static final class Account {
        private final String id;

        Account(String id) {
            this.id = id;
        }
    }
}
~~~

Trong ví dụ trên, code và class đích thuộc cùng ứng dụng đơn giản; JVM có thể cho phép suppress Java language access checks. Nhưng **setAccessible(true)** không phải giấy phép vượt mọi ranh giới JPMS. Nếu class đích thuộc named module khác và package không được mở tương ứng, thao tác có thể bị chặn.

Không nên dựa vào khả năng ghi tùy ý mọi private final field. Ngay cả khi một field có thể được quan sát qua reflection, khả năng sửa final field bị hạn chế bởi loại field và quy tắc runtime; việc sửa trạng thái immutable còn có nguy cơ phá vỡ invariant.

### 2.3. setAccessible và trySetAccessible

Hai API thường gặp:

- **setAccessible(true):** yêu cầu bỏ qua các kiểm tra truy cập ngôn ngữ Java nếu nền tảng cho phép; có thể ném **InaccessibleObjectException** khi bị module encapsulation chặn.
- **trySetAccessible():** thử bật quyền truy cập, trả về **false** nếu không thể cho phép thay vì ném InaccessibleObjectException trong trường hợp này.

Ví dụ:

~~~java
import java.lang.reflect.Field;

public final class SafeInspector {
    public static Object readIfAllowed(Object target, String fieldName)
            throws ReflectiveOperationException {
        Field field = target.getClass().getDeclaredField(fieldName);

        if (!field.trySetAccessible()) {
            throw new IllegalStateException(
                "Cannot access " + target.getClass().getName()
                    + "." + fieldName
            );
        }
        return field.get(target);
    }
}
~~~

**trySetAccessible()** không biến việc truy cập bị cấm thành hợp lệ. Nó chỉ cho phép chương trình xử lý tình huống bị từ chối có kiểm soát hơn. Với framework, nên ưu tiên API public hoặc extension point chính thức trước khi nghĩ tới việc mở quyền truy cập sâu.

## 3. JPMS: exports khác opens như thế nào?

Từ Java 9, Java Platform Module System (JPMS) cung cấp ranh giới module. Trong migration từ hệ thống classpath truyền thống sang named module, quy tắc truy cập có thể thay đổi rõ rệt.

### 3.1. exports: cung cấp API public

Module A có thể khai báo:

~~~java
module com.example.domain {
    exports com.example.domain.api;
}
~~~

Một module khác đọc module A có thể dùng các kiểu và thành viên public của package được export theo quy tắc Java thông thường. **exports** không cho phép một framework tùy ý mở private field hoặc private constructor bằng deep reflection.

### 3.2. opens: cho phép deep reflection

~~~java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.mapper;
}
~~~

Ở đây:

- **exports** cho phép truy cập public API trong package api.
- **opens ... to ...** cho phép module mapper thực hiện deep reflection vào package model.
- Package model không nhất thiết được export cho phép source của mọi consumer tham chiếu trực tiếp đến kiểu trong đó.
- Chỉ module có tên được cho phép mới có quyền deep reflection qua khai báo qualified opens này.

**opens** không đồng nghĩa với cho mọi module gọi API như thể package đã được exports; đây là hai cơ chế khác nhau.

### 3.3. Mẫu module-info cho ứng dụng

Ví dụ một ứng dụng sử dụng mapper có tên module xác định:

~~~java
module com.example.orders {
    requires com.example.mapper;

    exports com.example.orders.api;
    opens com.example.orders.entity to com.example.mapper;
}
~~~

Trong thực tế, **com.example.mapper** ở đây là tên giả định, không phải tên module chuẩn của Jackson hay Hibernate. Cần xác nhận tên module thật, ví dụ bằng mô tả module của JAR và module graph runtime, trước khi thay thế.

Nếu nhiều framework cùng cần reflective access, liệt kê đúng module cần thiết hoặc lựa chọn cấu trúc module phù hợp. Không mở toàn bộ package chỉ để tránh khảo sát dependency.

### 3.4. open module

Có thể khai báo:

~~~java
open module com.example.legacy {
    requires java.sql;
}
~~~

Một **open module** cho phép deep reflection vào các package của nó theo cơ chế module. Điều này có thể giúp chuyển đổi code legacy, nhưng mở phạm vi rộng hơn khai báo **opens** riêng từng package.

Với ứng dụng mới hoặc migration có khả năng kiểm soát, nên ưu tiên **qualified opens** hoặc mở package cụ thể, sau đó thu hẹp quyền khi framework đã hỗ trợ API public phù hợp.

### 3.5. Classpath, unnamed module và automatic module

- Code trên **classpath** thường thuộc unnamed module; các package của nó không bị encapsulation theo cùng cách với named module do ứng dụng định nghĩa.
- Một JAR được đưa lên **module path** có thể trở thành named automatic module nếu không có module descriptor.
- Automatic module có quy tắc exports/opens thuận tiện cho chuyển đổi; khi bổ sung module-info.java thực sự, quyền truy cập có thể trở nên chặt chẽ hơn.
- Code trong named module phải xem xét cả **readability**, exports và opens; chỉ thêm module path chưa đủ để bảo đảm reflection thành công.

Vì vậy, một ứng dụng chạy được trên classpath nhưng lỗi khi chuyển sang module path có thể đang phụ thuộc vào reflective access vốn trước đó không bị hạn chế.

## 4. Strong encapsulation và API nội bộ JDK

Các bản JDK hiện đại siết chặt quyền truy cập vào những phần nội bộ của JDK. Từ Java 17, strong encapsulation của phần lớn internal API được thực thi chặt chẽ hơn theo JEP 403; cơ chế nới lỏng rộng bằng tùy chọn cũ **--illegal-access** không còn là chiến lược khả dụng để khôi phục hành vi trước đây.

Một thư viện cũ có thể từng thực hiện:

~~~java
Class<?> type = Class.forName("java.lang.String");
var field = type.getDeclaredField("value");
field.setAccessible(true);
~~~

Việc lấy thông tin về field không đồng nghĩa được phép đọc private field. Khi truy cập bị JPMS chặn, lỗi điển hình là:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... accessible:
module java.base does not "opens java.lang" to ...
~~~

Thông báo lỗi nêu rõ **module/package** bị đóng và **module người gọi** cần quyền truy cập. Cần đọc chính xác những phần này thay vì áp dụng cờ chung chung cho toàn hệ thống.

### 4.1. --add-opens là gì?

Tùy chọn runtime:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

cho phép deep reflection từ code thuộc unnamed module vào package **java.lang** của module **java.base**. Đây chỉ là ví dụ kỹ thuật về phạm vi mở, không phải khuyến nghị thêm cờ này mặc định.

Cú pháp tổng quát:

~~~text
--add-opens=<module>/<package>=<target-module>
~~~

**ALL-UNNAMED** đại diện cho các unnamed module. Với consumer là named module, dùng tên module thích hợp làm target.

### 4.2. --add-exports không thay thế --add-opens

| Tùy chọn | Mục đích | Điều không làm được |
|---|---|---|
| **--add-exports** | Nới quyền truy cập public types/members trong package không export | Không tự mở private fields/methods cho deep reflection |
| **--add-opens** | Mở package cho deep reflection của target module | Không phải phương án dài hạn để phụ thuộc internal JDK API |
| **--add-reads** | Bổ sung quan hệ module readability | Không tự mở private members |
| **opens** trong module-info.java | Cấp quyền deep reflection từ module chủ sở hữu package | Không tương đương exports public API |

Lạm dụng **--add-opens** có thể che giấu việc dependency chưa hỗ trợ JDK mục tiêu. Cách bền vững là nâng thư viện hoặc thay thiết kế để không dùng internal JDK API.

### 4.3. Hướng xử lý theo thứ tự ưu tiên

1. Xác định package/module thực sự bị chặn.
2. Xác định thư viện và phiên bản thực hiện reflective access.
3. Kiểm tra bản cập nhật tương thích với JDK mục tiêu.
4. Ưu tiên API Java chuẩn hoặc API framework công khai.
5. Nếu đó là package do ứng dụng sở hữu, cân nhắc **opens** có phạm vi hẹp.
6. Nếu phải dùng **--add-opens** để chuyển tiếp, ghi lý do, target, owner và thời hạn loại bỏ.
7. Kiểm thử trên runtime thực tế và theo dõi khi nâng JDK tiếp theo.

Không coi mọi **InaccessibleObjectException** là lý do cho phép mở **java.base** toàn cục.

## 5. ORM: reflection để dựng và quản lý entity

ORM (Object-Relational Mapping) ánh xạ dữ liệu giữa bảng và đối tượng Java. Các triển khai như Hibernate/JPA thường dùng reflection, bytecode enhancement và proxy để:

- Đọc annotation của entity và property.
- Xác định trường định danh, relationship và mapping.
- Khởi tạo entity khi đọc dữ liệu từ database.
- Gán giá trị field hoặc gọi getter/setter tùy chiến lược access.
- Theo dõi thay đổi, lazy load và tương tác với proxy.
- Khởi tạo collection wrapper hoặc enhanced entity.

### 5.1. Ví dụ entity dùng field access

~~~java
package com.example.orders.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class CustomerEntity {
    @Id
    private Long id;

    private String name;

    protected CustomerEntity() {
        // Constructor phục vụ ORM
    }

    public CustomerEntity(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Trong kiểu mapping này, **@Id** đặt trên field, vì vậy ORM có thể sử dụng field-based access. Nó có thể cần truy cập field private bằng reflection hoặc cơ chế enhanced bytecode phù hợp.

Một số ràng buộc quan trọng:

- Jakarta Persistence yêu cầu entity có constructor không tham số với quyền public hoặc protected.
- Provider có thể có giới hạn đối với class hoặc method final khi dùng proxy/lazy loading.
- Khi module hóa ứng dụng, package entity có thể cần được mở cho module của provider ORM.
- Mapping private field cần test trong môi trường module path/runtime thật.

Đừng kết luận rằng mọi entity phải công khai toàn bộ field để ORM hoạt động. Vấn đề là cơ chế truy cập nào được mapping chọn và quyền truy cập nào runtime cho phép.

### 5.2. Field access và property access

| Chiến lược | Cách mapping đọc/ghi giá trị | Rủi ro migration |
|---|---|---|
| Field access | Làm việc với field, có thể cả private field | JPMS opens, field name, access rules, enhancement |
| Property access | Làm việc với getter/setter theo quy tắc mapping | Visibility, method signatures, bean conventions |
| Bytecode enhancement | Chèn hoặc điều chỉnh bytecode để theo dõi/truy cập | Hỗ trợ class file version, build plugin và runtime agent |
| Proxy-based lazy loading | Tạo proxy/ủy quyền để tải dữ liệu khi cần | Final class/method, constructor, class loader, package/module |

Khi nâng ORM, không nên thay toàn bộ field access thành property access như một cách sửa nhanh nếu chưa xác nhận hành vi mapping. Thay access strategy có thể tác động đến tên thuộc tính, dirty checking, lazy loading và serialization.

### 5.3. JPMS với entity

Giả sử module ứng dụng sở hữu entity:

~~~java
module com.example.orders {
    requires jakarta.persistence;

    exports com.example.orders.api;
    opens com.example.orders.entity to com.example.persistence.provider;
}
~~~

**com.example.persistence.provider** chỉ là tên minh họa. Trên dự án thực, phải dùng tên module của provider thực tế. Cũng cần xem provider chạy trên module path hay classpath, có sử dụng nhiều module hỗ trợ hay không, và tài liệu chính thức quy định cấu hình nào.

Nếu ứng dụng đang dùng classpath, việc thêm module-info.java trong migration có thể tạo lỗi mới dù không thay đổi entity source.

### 5.4. Reflection và proxy là hai ràng buộc khác nhau

Một entity có thể được tạo và gán field bằng reflection nhưng vẫn gặp lỗi lazy loading do proxy không tạo được subclass.

Ví dụ:

~~~java
@Entity
public final class InvoiceEntity {
    @Id
    private Long id;

    protected InvoiceEntity() {
    }
}
~~~

Một số cơ chế proxy dựa trên subclass không thể kế thừa class final. Nhưng việc class là final không tự chứng minh mọi ORM hoặc mọi đường truy cập đều thất bại; provider có thể dùng enhancement hoặc cơ chế khác.

Vì vậy cần kiểm thử riêng:

1. Persist một entity.
2. Load entity từ database.
3. Truy cập relationship lazy.
4. Gọi method cần interception.
5. Kiểm tra proxy/enhancement thực tế được provider sử dụng.

### 5.5. Java EE sang Jakarta EE

Một migration framework lớn có thể đồng thời đổi package từ **javax.persistence** sang **jakarta.persistence**. Đây là vấn đề API/dependency khác với encapsulation, nhưng chúng thường xuất hiện cùng lúc.

Nếu một ứng dụng gặp lỗi entity không được nhận diện, không nên chỉ thêm **--add-opens**. Hãy kiểm tra đúng bộ thư viện Jakarta/Hibernate, annotation namespace, provider và phiên bản JDK trước khi điều tra reflective access.

## 6. Serializer: reflection cho JSON, XML và dữ liệu trao đổi

Serializer/deserializer cần biến object thành dữ liệu và tái tạo object từ dữ liệu. Thư viện như Jackson có thể dựa trên:

- Getter/setter public.
- Field visibility.
- Annotation chỉ định tên property.
- Constructor hoặc factory method.
- Record component.
- Generic type metadata.
- Polymorphic type information.
- Converter cho kiểu đặc biệt.

### 6.1. DTO có public accessor

~~~java
package com.example.api;

public final class UserDto {
    private final String id;
    private final String displayName;

    public UserDto(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Serialization có thể hoạt động thông qua accessor public. Tuy nhiên, deserialization cần cách tạo object phù hợp. Một serializer có thể không suy ra đúng constructor argument nếu thiếu metadata hoặc cấu hình cần thiết.

### 6.2. Constructor được khai báo tường minh

Ví dụ Jackson với creator:

~~~java
package com.example.api;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class UserDto {
    private final String id;
    private final String displayName;

    @JsonCreator
    public UserDto(
            @JsonProperty("id") String id,
            @JsonProperty("displayName") String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Việc chỉ rõ creator và property names giúp hợp đồng dữ liệu dễ nhận diện. Nó không tự giải quyết mọi vấn đề JPMS: module chứa DTO vẫn phải export hoặc open package phù hợp với cách framework truy cập constructor/method.

### 6.3. Record và reflection

Java record có thể phù hợp với DTO immutable:

~~~java
package com.example.api;

public record UserView(String id, String displayName) {
}
~~~

Record cung cấp component, accessor và canonical constructor theo định nghĩa ngôn ngữ. Một thư viện serializer hỗ trợ record có thể đọc metadata này mà không cần thay đổi private final field.

Nhưng cần kiểm tra phiên bản cụ thể của thư viện serializer: không phải mọi phiên bản cũ đều hiểu record hoặc cách tạo instance đúng. Khi nâng JDK và serializer đồng thời, lỗi có thể đến từ thiếu hỗ trợ record, không nhất thiết từ JPMS.

### 6.4. Field visibility và rủi ro mở quyền quá rộng

Một số serializer có chế độ khám phá mọi private field. Điều này tiện cho model cũ nhưng tạo thêm phụ thuộc vào implementation và quyền reflective access.

Ví dụ logic cấu hình có thể mở rộng phạm vi field discovery:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.setVisibility(
    PropertyAccessor.FIELD,
    JsonAutoDetect.Visibility.ANY
);
~~~

Đoạn này chỉ minh họa hướng cấu hình; trên dự án thật cần import và dependency Jackson phù hợp.

Hệ quả có thể là:

- Trường nội bộ bị đưa vào JSON ngoài ý muốn.
- Đổi tên private field thành thay đổi dữ liệu.
- Object graph gây vòng lặp hoặc lazy loading không chủ đích.
- Private field thuộc named module bị chặn khi framework cố truy cập.
- Các quy tắc bảo mật dữ liệu dễ bị bỏ qua nếu chỉ dựa vào mặc định serializer.

Ưu tiên DTO có hợp đồng rõ ràng cho API công khai thay vì serialize trực tiếp entity hoặc mọi private field.

### 6.5. Contract trước và sau migration

Giả sử DTO cũ có field **customerId**, nhưng phiên bản mới đổi tên thành **id**. Nếu serializer tự dùng field name, JSON output có thể đổi từ:

~~~json
{"customerId":"C-001"}
~~~

sang:

~~~json
{"id":"C-001"}
~~~

Mã Java vẫn compile; binary compatibility của class cũng có thể không phải vấn đề chính. Tuy nhiên, consumer API cũ đang đọc **customerId** sẽ thất bại.

Do đó, test serializer cần so sánh JSON/XML contract và dữ liệu thực, không chỉ kiểm tra rằng **ObjectMapper** chạy không ném exception.

## 7. Dynamic proxy, AOP và reflection

Proxy là đối tượng trung gian nhận lời gọi thay cho đối tượng đích. Reflection thường được dùng để xác định interface, method và dispatch. Một số cơ chế proxy tạo class mới tại runtime.

### 7.1. JDK dynamic proxy cho interface

Ví dụ dùng Java chuẩn:

~~~java
package com.example.proxy;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ProxyDemo {
    public interface PaymentService {
        String pay(String invoiceId);
    }

    public static final class RealPaymentService implements PaymentService {
        @Override
        public String pay(String invoiceId) {
            return "paid:" + invoiceId;
        }
    }

    public static void main(String[] args) {
        PaymentService target = new RealPaymentService();

        InvocationHandler handler = (proxy, method, arguments) -> {
            System.out.println("calling " + method.getName());
            return method.invoke(target, arguments);
        };

        PaymentService proxy = (PaymentService) Proxy.newProxyInstance(
            PaymentService.class.getClassLoader(),
            new Class<?>[]{PaymentService.class},
            handler
        );

        System.out.println(proxy.pay("INV-001"));
    }
}
~~~

JDK dynamic proxy chủ yếu dựa trên interface. Nó tạo một class có thể được dùng dưới kiểu interface và chuyển lời gọi đến **InvocationHandler**. Đây không phải cách tạo subclass trực tiếp của class concrete bất kỳ.

Lưu ý với ví dụ:

- **method.invoke()** có thể bọc exception do target ném trong **InvocationTargetException**. Một handler production cần xử lý phù hợp.
- Các method của **Object**, default interface methods và exception declarations có những quy tắc dispatch riêng.
- Interface phải đáp ứng điều kiện visibility/module/package của cơ chế Proxy.
- Một proxy có thể tạo thành công nhưng hành vi transaction, security hoặc exception mapping vẫn cần test riêng.

### 7.2. Proxy dựa trên subclass

CGLIB, Byte Buddy hoặc framework AOP có thể tạo subclass và override method để chèn hành vi.

~~~text
Client
   |
   v
Proxy subclass
   |
   | intercept method
   v
Target logic
~~~

Ràng buộc thường gặp:

- Class **final** không thể được subclass.
- Method **final** không thể được override.
- Method private không thể được override.
- Constructor và class loader có thể ảnh hưởng cách tạo instance.
- JPMS access và package placement có thể ảnh hưởng class generation.
- Class **sealed** giới hạn direct subclasses, gây khó khăn cho generated subclass không nằm trong permits.

Khi migration, đừng kết luận rằng chỉ cần đổi từ JDK proxy sang class proxy là sẽ luôn giải quyết được lỗi. Hai cơ chế có hợp đồng kiểu và ràng buộc khác nhau.

### 7.3. Spring AOP: interface proxy và class proxy

Ở Spring AOP, framework có thể tạo proxy dựa trên interface hoặc dựa trên class tùy cấu hình và điều kiện. Khi proxy dựa trên class, final class/method có thể khiến phần advice không áp dụng theo cách mong muốn.

Ví dụ:

~~~java
public class BillingService {
    public final void charge() {
        // Business logic
    }
}
~~~

Nếu logic AOP cần override **charge()** trong subclass proxy, method final ngăn cơ chế đó. Nhưng nếu hệ thống đang dùng interface proxy và gọi qua interface, các ràng buộc có thể khác.

Một tình huống dễ nhầm là **self-invocation**: lời gọi từ method này sang method khác bên trong chính object có thể bỏ qua proxy bên ngoài, khiến advice không chạy. Đây là rủi ro hành vi AOP; thêm **--add-opens** không giải quyết được nó.

### 7.4. Proxy và sealed hierarchy

Nếu framework muốn tạo direct subclass của một sealed class hoặc direct implementation của sealed interface, generated type phải tuân thủ tập permitted. Với thư viện cần extension động, thiết kế sealed có thể không phù hợp hoặc cần nhánh **non-sealed** rõ ràng.

Đừng sử dụng cờ reflective access để cố vượt quy tắc **final/sealed**: đây là quy tắc kế thừa và xác minh class, không phải chỉ là quyền đọc private field.

## 8. Thư viện kiểm thử và reflection

Framework kiểm thử có thể dùng reflection để tìm và gọi test method, xử lý annotation, tạo đối tượng test, inject dependency hoặc mô phỏng lời gọi.

### 8.1. JUnit và test discovery

JUnit Jupiter thường khám phá method được gắn annotation như **@Test** và gọi chúng theo lifecycle thích hợp.

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsNumbers() {
        assertEquals(4, 2 + 2);
    }
}
~~~

Việc test method không public vẫn có thể được framework xử lý tùy framework và cơ chế truy cập. Khi test class chuyển vào named module, module boundary có thể ngăn test engine truy cập reflective vào package chưa được mở.

Không nên giải quyết lỗi này bằng cách biến mọi method thành public nếu yêu cầu test framework là deep reflection vào package. Hãy xác minh module setup, tên module test engine và cách build tool tổ chức test source.

### 8.2. Mockito, Byte Buddy và instrumentation

Mockito và các thư viện mocking thường dùng nhiều kỹ thuật:

- Tạo mock dựa trên interface hoặc subclass.
- Sinh bytecode cho class mock.
- Dùng Java instrumentation/agent cho một số kiểu mock hoặc tình huống.
- Khám phá method/constructor bằng reflection.
- Thay đổi dispatch để ghi nhận lời gọi và cấu hình hành vi.

Khi nâng JDK, một bản Mockito/Byte Buddy cũ có thể chưa hỗ trợ class file version mới. Lỗi lúc tạo mock không nhất thiết là do business class có private field hoặc module thiếu opens.

Một số mock maker có thể hỗ trợ mock final class theo cơ chế instrumentation, trong khi kiểu mock khác dùng subclass và không thể kế thừa final class. Phải xem phiên bản Mockito, cấu hình mock maker và JDK đang dùng.

### 8.3. Agent và chính sách runtime

Các cơ chế instrumentation có thể sử dụng Java agent được chỉ định từ startup hoặc dynamic attachment. Chính sách và cảnh báo của JDK về agent có thể thay đổi theo release.

Khi migration:

- Đọc cảnh báo JVM thực tế về agent attach.
- Xác định thư viện nào gọi agent hoặc attach API.
- Xem tài liệu của Mockito/Byte Buddy/JDK tương ứng.
- Ưu tiên cấu hình agent chính thức mà nhà cung cấp hỗ trợ.
- Đừng tắt cảnh báo hoặc mở quyền toàn cục khi chưa hiểu lý do.

Test có thể thất bại trong CI nhưng thành công trên IDE vì cách khởi chạy JVM, quyền attach hoặc security policy của runner khác nhau.

### 8.4. JaCoCo và class file version

Một công cụ coverage sử dụng bytecode instrumentation như JaCoCo phải hỗ trợ phiên bản class file do JDK mới tạo ra. Lỗi liên quan đến unsupported class file version hoặc instrumentation failure có thể đến từ bản coverage tool cũ.

Trong tình huống này, thêm **--add-opens** không thay thế việc nâng JaCoCo hoặc thư viện bytecode xử lý.

### 8.5. Test framework không phải môi trường runtime production

Test suite có thể chủ động mở package, dùng agent và mock maker mà production không có. Do đó:

- Test thành công không bảo đảm production reflection thành công.
- Production chạy được không bảo đảm test suite hoạt động trên JDK mới.
- Cần kiểm thử cả hai bằng JVM arguments và dependency graph thực tế của từng môi trường.
- Nếu test thêm cờ tạm thời, ghi rõ cờ đó dùng cho test hay cả production.

## 9. Phân biệt các lỗi reflection thường gặp

| Lỗi / triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra đầu tiên |
|---|---|---|
| **InaccessibleObjectException** | setAccessible bị module encapsulation chặn | Đọc module/package/caller trong thông báo |
| **IllegalAccessException** | Thao tác reflective không được phép theo access rules | Visibility, exports/opens, caller |
| **NoSuchFieldException** | Field không tồn tại theo tên hoặc cách tìm kiếm | Tên, class thực tế, declared/inherited |
| **NoSuchMethodException** | Không tìm được method/constructor theo chữ ký | Parameter types, overload, visibility |
| **InvocationTargetException** | Method/constructor được gọi đã ném exception | Xem **getCause()** để tìm lỗi gốc |
| **ExceptionInInitializerError** | Static initialization của class thất bại | Cause và static initializer |
| **IncompatibleClassChangeError** | Quan hệ binary thay đổi, như final/sealed | So sánh class file cũ/mới và hierarchy |
| **NoClassDefFoundError** | Class cần thiết không thể được nạp hoặc khởi tạo | Runtime dependency và cause |
| **ClassCastException** | Proxy/object không phải kiểu consumer mong đợi | Interface/class proxy và class loader |
| **UndeclaredThrowableException** | JDK proxy bọc checked exception không khai báo | InvocationHandler và cause |
| **UnsupportedClassVersionError** | Bytecode không phù hợp với runtime | JDK compiler, class major version, JDK runtime |
| **VerifyError** | Bytecode hoặc quan hệ kiểu không hợp lệ khi verify | Bytecode instrumentation/version và dependency |
| Mockito mock creation failure | Byte Buddy/mock maker/agent không tương thích | Phiên bản Mockito, Byte Buddy, agent và JDK |
| Entity lazy-loading failure | Proxy/enhancement, session, hierarchy hoặc mapping | ORM logs, entity modifier, access mode |
| JSON output thay đổi | Cấu hình serializer hoặc property discovery đổi | Contract/golden JSON comparison |

Một lỗi có thể có nhiều nguyên nhân. Ví dụ, **NoSuchMethodException** có thể do tên method đổi, tham số khác hoặc framework tìm constructor mặc định không tồn tại; nó không mặc nhiên là lỗi JPMS.

### 9.1. Điều tra cause chain, không chỉ top-level exception

~~~java
try {
    method.invoke(target);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable cause = ex.getCause();
    System.err.println("Underlying failure: " + cause);
    throw ex;
}
~~~

Exception do target method ném được reflection bọc lại. Khi đọc stack trace dài của framework, hãy tìm **Caused by** sâu nhất nhưng cũng xem bối cảnh tạo proxy/serializer để xác định đường gọi.

### 9.2. Lỗi do class loader

Hai class có cùng fully qualified name nhưng được nạp bởi class loader khác nhau có thể được JVM xem là những runtime types khác nhau. Plugin architecture, application server hoặc custom test class loader có thể tạo trường hợp này.

Triệu chứng thường là **ClassCastException**, không liên quan trực tiếp đến **setAccessible**. Khi kiểm tra, xem class loader của class đích, class loader tạo proxy và JAR được nạp ở runtime.

## 10. Công cụ khảo sát khi migration

### 10.1. In phiên bản Java và thông tin module

~~~bash
java -version
javac -version
java --list-modules
~~~

Trong ứng dụng đang chạy có thể kiểm tra:

~~~java
Class<?> targetClass = SomeType.class;

System.out.println("module=" + targetClass.getModule().getName());
System.out.println("package=" + targetClass.getPackageName());
System.out.println("loader=" + targetClass.getClassLoader());
~~~

Nếu module name là **null**, class thường thuộc unnamed module. Đừng suy luận rằng thiếu tên module nghĩa là JVM không áp dụng bất kỳ quy tắc truy cập nào khác.

### 10.2. jdeps để tìm phụ thuộc vào JDK internal API

~~~bash
jdeps --jdk-internals app.jar
~~~

Lệnh này hỗ trợ phát hiện một số tham chiếu tĩnh đến API nội bộ JDK trong bytecode. Tuy nhiên, tham chiếu được tạo từ chuỗi tên class rồi gọi reflection có thể không bị phát hiện; kết quả sạch không chứng minh rằng ứng dụng hoàn toàn không dùng internal API.

### 10.3. javap để xem bytecode và modifiers

~~~bash
javap -classpath app.jar -p -v com.example.api.SomeType
~~~

Có thể xem:

- Method descriptor.
- Constructor và access flags.
- Final/sealed-related metadata.
- Superclass và interface.
- Annotation và class-file version.

Dùng nó để xác minh artifact thực sự đang được triển khai, không chỉ source trong working tree.

### 10.4. Dấu vết module resolution và JVM command line

Có thể chạy:

~~~bash
java --show-module-resolution --module-path mods --module com.example.app/com.example.Main
~~~

Nếu đang điều tra process đã chạy, công cụ như **jcmd** có thể cung cấp thông tin JVM và command line trong phạm vi quyền truy cập cho phép.

Điểm cần lưu lại gồm JDK vendor/version, module path/classpath, JVM arguments, build artifact checksum và dependency graph. Các thông tin này giúp phân biệt lỗi do code với lỗi do môi trường.

## 11. Cấu hình Gradle khi framework cần reflective access

Đối với ứng dụng module hóa, ưu tiên cấu hình **module-info.java** với **opens**. Với test process trên classpath cần quyền vào package named module, có thể dùng **--add-opens** có phạm vi cụ thể.

Ví dụ Gradle Groovy DSL cho test JVM:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens=com.example.domain/com.example.domain=ALL-UNNAMED'
}
~~~

Ví dụ giả định module được mở là **com.example.domain**, package cũng tên **com.example.domain**. Phải thay bằng tên thực tế của module và package.

Nếu các module test là named modules, target có thể là tên named module thay vì **ALL-UNNAMED**.

### 11.1. Cờ test khác cờ compiler

- **javac options:** điều khiển biên dịch và module access cần thiết ở compile time.
- **Test JVM arguments:** áp dụng cho tiến trình chạy JUnit/Mockito/ORM/serializer test.
- **JavaExec JVM arguments:** áp dụng cho tiến trình được JavaExec khởi chạy.
- **Production JVM arguments:** áp dụng cho tiến trình ứng dụng thực tế.

Đặt **--add-opens** trong một Test task không tự động truyền sang application process. Đặt flag cho Gradle daemon cũng không có nghĩa mọi process được fork sẽ nhận flag.

### 11.2. Chẩn đoán task chạy bằng JVM nào

~~~bash
./gradlew -version
./gradlew test --info
~~~

Đối chiếu log và cấu hình toolchain để biết JDK chạy Gradle, JDK compiler và JDK test worker. Trên Windows dùng **gradlew.bat** tương ứng.

Không chạy task build chỉ để “xác nhận” tài liệu hướng dẫn migration nếu workflow hiện tại chỉ yêu cầu viết lesson; những lệnh trên là ví dụ cho người học thực hành trong dự án phù hợp.

## 12. Cấu hình Maven Surefire và Failsafe

Maven có thể fork test JVM qua Surefire hoặc Failsafe. Nếu cần một mở package tạm thời cho test, có thể đặt runtime argument:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>
            --add-opens=com.example.domain/com.example.domain=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
~~~

Cần cấu hình tương ứng cho Failsafe nếu integration test cũng cần access. Nếu dự án đang dùng JaCoCo, debugger hoặc Java agent có **argLine** riêng, phải hợp nhất đúng cách để không ghi đè arguments khác.

Nếu Surefire không fork JVM, cờ cho process con không tự thay đổi JVM đã khởi chạy Maven. Cấu hình phải tương ứng với chế độ test thực tế.

Đừng thêm opens cho toàn bộ ứng dụng chỉ vì một test fixture cần truy cập một private field. Hãy xem lại cách viết test hoặc mở quyền riêng cho test module trước.

## 13. Chiến lược sửa lỗi bền vững

Khi gặp lỗi reflection, ưu tiên cách giải quyết có phạm vi nhỏ nhất và ít phụ thuộc nhất vào chi tiết nội bộ.

### 13.1. Thứ tự gợi ý

1. **Xác nhận lỗi gốc:** đọc exception, cause chain, JDK, module và JAR thực tế.
2. **Xác định actor:** ORM, serializer, proxy, test framework hay application reflection?
3. **Kiểm tra dependency compatibility:** thư viện có hỗ trợ JDK và framework mục tiêu không?
4. **Nâng dependency phù hợp:** ưu tiên bản có hỗ trợ chính thức và giải quyết lỗi.
5. **Dùng API public/contract rõ ràng:** accessor, constructor, creator, DTO, extension interface.
6. **Mở package có chủ đích:** khi package do ứng dụng sở hữu và framework thật sự cần deep reflection.
7. **Dùng --add-opens có kiểm soát:** chỉ khi là biện pháp chuyển tiếp có owner và kế hoạch loại bỏ.
8. **Viết regression test:** kiểm chứng đúng đường ORM/JSON/proxy/mock đã từng hỏng.

### 13.2. Không mở JDK internal package chỉ để “hết lỗi”

Một lệnh **--add-opens=java.base/java.lang=ALL-UNNAMED** có thể giúp một dependency cũ đi qua một lỗi encapsulation cụ thể. Nhưng nó không bảo đảm dependency tương thích với class file mới, security policy, module graph hoặc hành vi runtime của JDK mới.

Cờ cũng có thể bị phân tán giữa môi trường local, CI, staging và production. Nếu quên một nơi, lỗi sẽ quay lại.

### 13.3. Không serialize trực tiếp entity khi không cần thiết

Dùng DTO ổn định cho API công khai giúp tách:

- Data contract của consumer.
- Mapping và lazy-loading semantics của ORM.
- Private field/constructor của entity.
- Cấu trúc module bên trong ứng dụng.

DTO không giải quyết mọi lỗi reflection, nhưng giảm số nơi buộc serializer biết chi tiết ORM.

### 13.4. Thiết kế extension thay vì hack private member

Nếu plugin hoặc test cần một trạng thái bên trong, cân nhắc API truy vấn, hook hoặc test fixture phù hợp thay vì phản chiếu vào private field. Một dependency trực tiếp vào tên field private rất dễ hỏng khi refactor dù không nâng JDK.

## 14. Tình huống migration tổng hợp: JDK cũ lên JDK mới

Giả sử hệ thống Java chạy trên một JDK cũ, dùng ORM, Jackson, Spring AOP và Mockito. Sau khi nâng JDK, có ba nhóm lỗi:

1. ORM không khởi tạo entity trong named module.
2. Serializer thất bại khi đọc một private field của DTO.
3. Test suite không tạo được mock cho một class final.

Không nên mặc định cả ba lỗi có cùng nguyên nhân hoặc cùng giải pháp.

### Giai đoạn A: Chốt baseline

Ghi lại:

- JDK, Gradle/Maven, framework và dependency phiên bản hiện tại.
- Artifact đã phát hành và checksum.
- Các module-info.java nếu có.
- JVM flags của application, CI và test.
- Hợp đồng JSON/XML trước migration.
- Integration test đại diện cho ORM, serializer và proxy.

### Giai đoạn B: Phân loại và khoanh vùng

| Sự cố | Khả năng nguyên nhân | Bằng chứng cần lấy |
|---|---|---|
| ORM entity thất bại | Package entity không mở, provider cũ hoặc constructor không phù hợp | Full stack trace, entity mapping, module graph |
| JSON private field thất bại | Deep reflection bị từ chối hoặc property discovery đổi | InaccessibleObjectException, serializer version, payload |
| Mock final class thất bại | Mock maker/Byte Buddy/agent không tương thích | Mockito version, JDK, mock configuration |
| Proxy advice không chạy | Final method/class, interface/class proxy hoặc self-invocation | Runtime proxy type, call path, test advice |
| Lỗi class file trong coverage | JaCoCo/bytecode library chưa hỗ trợ target | Major version, tool versions, stack trace |

### Giai đoạn C: Sửa theo nguyên nhân

- ORM: cập nhật provider tương thích, xác nhận mapping/constructor, cấu hình module opens hẹp nếu cần.
- Serializer: nâng thư viện, dùng constructor/creator rõ ràng, điều chỉnh DTO, kiểm tra module access.
- Mocking: nâng mock framework và bytecode tools theo tài liệu, xác định cơ chế agent; không tự động thêm opens cho mọi package.
- Proxy: kiểm tra modifier và chiến lược proxy, thay thiết kế extension nếu cần.
- Coverage: nâng tool hỗ trợ class-file version mới.

### Giai đoạn D: Kiểm chứng

Chạy lại chính các tình huống đã thất bại và thêm acceptance criteria rõ ràng:

- ORM persist, load và lazy relationship trên JDK mới.
- JSON serialize/deserialize với dữ liệu cũ và mới; không đổi contract ngoài kế hoạch.
- Proxy thực thi advice đúng một lần ở các luồng nghiệp vụ cần thiết.
- Mockito tạo mock và xác minh hành vi trên test runner mục tiêu.
- Không còn yêu cầu mở package JDK nội bộ không có owner hoặc lý do.
- CI, staging và production sử dụng dependency/runtime configuration được kiểm soát.

## 15. Kiểm thử tương thích theo ma trận

Một bộ test chỉ chạy trên một JDK và một kiểu deployment có thể bỏ sót khác biệt giữa môi trường.

| Trục kiểm thử | Các trạng thái cần cân nhắc |
|---|---|
| JDK | Baseline, target; các version được tuyên bố hỗ trợ |
| Layout | Classpath, module path nếu dự án hỗ trợ cả hai |
| ORM | Field access, property access, lazy loading, enhancement |
| Serializer | Serialize, deserialize, constructor, record, nullable/unknown properties |
| Proxy | Interface proxy, class proxy, final method, self-invocation |
| Test | JUnit discovery, Mockito mock maker, coverage, integration test |
| Deployment | Local, CI worker, container runtime, staging |
| Consumer | Consumer hiện tại và consumer cũ đã biên dịch nếu cần binary compatibility |

Không nhất thiết chạy mọi tổ hợp tích Descartes. Chọn trường hợp theo rủi ro và support policy, đặc biệt nơi có module boundary hoặc dependency khác nhau.

### 15.1. Golden data test cho serializer

Lưu những payload đại diện để so sánh output:

~~~json
{
  "id": "C-001",
  "name": "Nguyen An",
  "active": true
}
~~~

Kiểm tra:

- Tên field giữ nguyên trừ khi có quyết định versioning.
- Kiểu dữ liệu, null và trường không xác định được xử lý nhất quán.
- Polymorphic payload nếu ứng dụng dùng type metadata.
- Không vô tình lộ private field nội bộ.
- Có thể đọc payload cũ trên bản mới theo hợp đồng đã công bố.

### 15.2. Regression test cho ORM

Một bài test tích hợp nên:

1. Tạo entity qua đường nghiệp vụ.
2. Persist và flush.
3. Clear persistence context.
4. Load entity theo id.
5. Truy cập relationship cần lazy loading trong transaction phù hợp.
6. So sánh trạng thái và hành vi mapping.

Kiểm thử này phải chạy với provider, database configuration và module layout đại diện. Test bằng mock repository đơn thuần không chứng minh ORM reflection/lazy proxy hoạt động.

### 15.3. Regression test cho AOP/proxy

Một test nên gọi method từ bên ngoài qua bean/proxy thực tế, rồi xác nhận advice cần thiết đã được áp dụng. Nếu muốn kiểm tra self-invocation, tạo thêm test riêng cho lời gọi nội bộ để thấy sự khác biệt.

Không gọi trực tiếp target object rồi kết luận proxy hoạt động.

### 15.4. Regression test cho mocking

Các test cần xác minh:

- Mock tạo được trên JDK target.
- Final class/method nếu được dùng trong test có cơ chế hỗ trợ đúng.
- Test không phụ thuộc dynamic attach bị môi trường CI cấm ngoài dự kiến.
- Coverage agent và mocking agent không xung đột.
- Không có cảnh báo runtime mới bị bỏ qua mà không có phân tích.

## 16. Những sai lầm thường gặp

### 16.1. Chỉ nâng JDK, giữ nguyên toàn bộ bytecode tools

Mocking, coverage, proxy và ORM enhancement có thể phụ thuộc thư viện đọc/ghi class file. JDK mới thường đi kèm class-file version mới. Nếu tool không hỗ trợ version này, lỗi có thể phát sinh trước khi business code chạy.

Cách xử lý: khảo sát ma trận hỗ trợ của từng thư viện bytecode và nâng bản tương thích.

### 16.2. Thêm --add-opens theo kiểu thử từng cờ cho đến khi chạy

Cách này dễ tạo cấu hình bảo trì khó khăn. Khi phát hành, một flag bị thiếu trong container hoặc batch process có thể khiến lỗi xuất hiện lại.

Cách xử lý: xác định package/module/caller từ stack trace, sửa dependency hoặc thiết kế trước, chỉ dùng cờ hẹp như bước chuyển tiếp có ghi nhận.

### 16.3. Đổi tất cả field thành public

Công khai field làm thay đổi encapsulation và tăng rủi ro lộ dữ liệu. Nó cũng không tự sửa lỗi class-file instrumentation, proxy hoặc property mapping.

Cách xử lý: dùng public accessor/creator hợp đồng rõ, hoặc mở package có chọn lọc khi framework chính thức cần deep reflection.

### 16.4. Test trên classpath nhưng triển khai trên module path

Lỗi chỉ xuất hiện trong production vì module boundary khác với test.

Cách xử lý: có integration test theo layout và JVM arguments thực tế của deployment.

### 16.5. Nhầm lỗi reflective access với lỗi mapping

Một DTO deserialize sai có thể do thiếu constructor hoặc annotation, không phải module đóng. Một entity lazy load thất bại có thể do session đã đóng, không phải quyền private field.

Cách xử lý: đọc cause chain và xác định thao tác gây lỗi cụ thể.

### 16.6. Giả định proxy luôn dùng subclass

JDK proxy dựa trên interface khác cơ chế với class-based proxy. Một class final có thể không gây cùng hệ quả nếu hệ thống chỉ sử dụng interface proxy. Ngược lại, sealed interface có thể gây vấn đề cho generated implementation.

Cách xử lý: xác định loại proxy thật, class loader và contract method.

### 16.7. Chỉ chạy unit test có mock

Mock repository hoặc serializer có thể bỏ qua chính cơ chế reflection/proxy cần kiểm tra.

Cách xử lý: thêm integration test với ORM, JSON mapper và proxy thật trên runtime target.

## 17. Mẫu risk register và quyết định mở package

Khi phát hiện lỗi reflection, ghi lại để phân biệt workaround với giải pháp bền vững.

| Trường | Nội dung |
|---|---|
| Risk ID | Ví dụ REF-001 |
| Component | ORM, serializer, proxy hoặc testing |
| JDK baseline/target | Phiên bản đang di chuyển |
| Library version | Dependency và artifact thực tế |
| Failing operation | Field access, constructor, method, proxy generation |
| Exception | Tên lỗi và cause gốc |
| Module/package | Module/package bị chặn |
| Caller module | Module yêu cầu quyền |
| Root cause | Ví dụ provider cũ dùng deep reflection vào package đóng |
| Preferred fix | Upgrade library, public API, creator, qualified opens |
| Temporary workaround | Cờ và scope cụ thể nếu bắt buộc |
| Owner | Nhóm phụ trách |
| Acceptance evidence | Test ID, log, artifact checksum |
| Removal date | Khi nào bỏ workaround |
| Residual risk | Rủi ro còn lại |

Ví dụ:

~~~text
Risk ID: REF-001
Component: Serialization
Root cause: Mapper cần deep reflection vào model package
Preferred fix: DTO/creator rõ ràng và phiên bản mapper được hỗ trợ
Temporary workaround: Qualified opens chỉ cho module mapper
Evidence: JSON contract test + runtime integration test
Owner: API team
Done when: Không còn phụ thuộc vào JDK internal package
~~~

Một bản sửa chỉ được xem là hoàn tất khi có evidence chạy được trên target runtime. “Đã thêm flag” mới là hành động cấu hình, chưa phải bằng chứng tương thích.

## 18. Checklist trước khi hoàn tất migration

### Khảo sát

- [ ] Liệt kê ORM, serializer, proxy, mocking và coverage libraries đang dùng.
- [ ] Chốt phiên bản JDK, build tool và dependency baseline/target.
- [ ] Xác định ứng dụng chạy classpath hay module path.
- [ ] Xác định module/package chứa entity, DTO và các extension point.
- [ ] Tìm code dùng Class.forName, getDeclaredField, setAccessible hoặc MethodHandles private lookup.
- [ ] Xác nhận có sử dụng internal JDK API hay không.
- [ ] Lưu cấu hình JVM arguments của local, CI và production.

### Tương thích ORM và serializer

- [ ] ORM provider hỗ trợ JDK và framework mục tiêu.
- [ ] Entity mapping, constructor và field/property access được kiểm chứng.
- [ ] Lazy-loading proxy hoặc bytecode enhancement hoạt động.
- [ ] Serializer hỗ trợ DTO, record và constructor đang dùng.
- [ ] JSON/XML contract không đổi ngoài kế hoạch.
- [ ] Không xuất hiện private field ngoài ý muốn trong dữ liệu công khai.

### Proxy và kiểm thử

- [ ] Xác định interface-based hay class-based proxy thực tế.
- [ ] Đánh giá ảnh hưởng của final/sealed và class loader.
- [ ] Kiểm tra AOP interception và self-invocation.
- [ ] Mockito, Byte Buddy và coverage tool hỗ trợ JDK target.
- [ ] Test runner và agent được cấu hình theo môi trường thực.
- [ ] Có integration test không dựa hoàn toàn vào mock.

### JPMS và vận hành

- [ ] Phân biệt rõ exports, opens và add-opens.
- [ ] Qualified opens chỉ mở package cần thiết cho đúng module.
- [ ] Mọi --add-opens tạm thời có owner và kế hoạch loại bỏ.
- [ ] Không dùng --illegal-access như phương án khôi phục mặc định.
- [ ] CI, staging và production thống nhất JDK và JVM arguments.
- [ ] Đã lưu stack trace, test report, dependency graph và artifact checksum.
- [ ] Rủi ro còn lại có người chịu trách nhiệm và tiêu chí chấp nhận.

## 19. Tài liệu chính thức nên đối chiếu

Khi làm migration thực tế, đối chiếu với tài liệu của đúng JDK và framework:

- **Java Reflection API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/package-summary.html
- **AccessibleObject:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- **JPMS / JEP 261:** https://openjdk.org/jeps/261
- **Strong Encapsulation / JEP 403:** https://openjdk.org/jeps/403
- **Java Dynamic Proxy API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html
- **Java Module System (JLS):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7
- **Jakarta Persistence:** https://jakarta.ee/specifications/persistence/
- **Jackson:** https://github.com/FasterXML/jackson
- **Mockito:** https://site.mockito.org/
- **JUnit 5:** https://junit.org/junit5/

Tài liệu của framework, provider ORM và mocking tool cần được đối chiếu theo phiên bản cụ thể. Không có một tổ hợp **--add-opens** chung phù hợp cho mọi dự án.

---

**Kết luận:** Reflection là một hợp đồng runtime thường không hiển thị qua compiler. Khi nâng Java hoặc chuyển từ classpath sang module path, hãy xác định thư viện nào cần truy cập thành viên nào, phân biệt **exports** với **opens**, kiểm tra khả năng hỗ trợ JDK của ORM/serializer/proxy/testing tools và xác nhận bằng integration test trên runtime mục tiêu. Chỉ dùng mở quyền truy cập như giải pháp có phạm vi và bằng chứng; ưu tiên API công khai, DTO ổn định và dependency được hỗ trợ để giảm rủi ro lâu dài.
