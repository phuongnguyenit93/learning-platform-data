# Tên annotation, import và tên đầy đủ của kiểu trong Java

Khi sử dụng annotation, phần đứng sau dấu **@** là tên của một **kiểu annotation** (annotation type). Java phải tìm được đúng kiểu đó tại thời điểm biên dịch, giống như khi mã nguồn tham chiếu đến một class hoặc interface. Có thể viết tên ngắn khi kiểu đã nằm trong phạm vi nhận diện, hoặc viết tên đầy đủ gồm package để xác định chính xác kiểu cần dùng.

Bài này tập trung vào cách đặt tên, khai báo package, import và tham chiếu kiểu annotation. Phần đọc metadata bằng reflection chỉ được dùng để kiểm chứng rằng các cách viết khác nhau thực sự trỏ đến cùng một kiểu.

## 1. Tên của annotation là tên một kiểu Java

Một annotation tự định nghĩa được khai báo bằng **@interface**:

~~~java
package com.example.annotations;

public @interface Role {
    String value();
}
~~~

Trong ví dụ này:

- **Role** là tên đơn giản (*simple name*) của kiểu annotation; Java phân biệt chữ hoa và chữ thường.
- **com.example.annotations** là package khai báo kiểu.
- **com.example.annotations.Role** là tên được định danh đầy đủ (*fully qualified name*) của kiểu.
- **Role.java** là tên tệp nguồn bắt buộc tương ứng với khai báo kiểu public này.
- **value()** là một *annotation element*. Nó không phải tên của annotation; phần tử này nhận một giá trị kiểu String khi sử dụng.

Sau khi khai báo, có thể gắn annotation lên một vị trí được phép:

~~~java
@Role("admin")
class AdminService {}
~~~

Dấu **@** là cú pháp sử dụng annotation; **Role** vẫn là kiểu Java thông thường về mặt phân giải tên. Không tạo annotation bằng biểu thức **new Role()**. Ví dụ trên chỉ hợp lệ khi mã nguồn tìm thấy kiểu Role, khai báo của Role cho phép áp dụng vào class và phần tử value được cung cấp giá trị hợp lệ.

**@Role("admin")** là dạng rút gọn của **@Role(value = "admin")** vì phần tử có tên đặc biệt là **value**. Hai cách viết này không thay đổi cách Java tìm kiểu Role.

## 2. Tên ngắn và tên đầy đủ

Giả sử kiểu Role nằm trong package **com.example.annotations**, còn class dùng nó nằm trong **com.example.app**.

| Cách tham chiếu | Cú pháp | Khi nào dùng |
| --- | --- | --- |
| Tên ngắn (*simple name*) | **@Role("admin")** | Khi Role đã được nhìn thấy trong phạm vi hiện tại, chẳng hạn nhờ import |
| Tên đầy đủ (*fully qualified name*) | **@com.example.annotations.Role("admin")** | Khi muốn chỉ rõ đúng package mà không cần import kiểu Role |

Hai cách viết trên có thể tham chiếu **cùng một kiểu annotation**, không tạo hai annotation khác nhau. Ví dụ:

~~~java
package com.example.app;

import com.example.annotations.Role;

@Role("admin")
class FirstService {}

@com.example.annotations.Role("guest")
class SecondService {}
~~~

Ở đây dòng import cho phép dùng tên ngắn Role. Cách dùng tên đầy đủ ở SecondService vẫn hợp lệ dù đã có import; nó chỉ viết rõ cả package lẫn tên kiểu.

**Tên đầy đủ không có dấu @ ở bên trong.** Dấu @ được viết một lần, ngay trước tên: **@com.example.annotations.Role**, không phải **com.example.annotations.@Role**.

## 3. Cách import annotation

Một kiểu annotation được import bằng **import thông thường**, vì nó cũng là một kiểu:

~~~java
package com.example.app;

import com.example.annotations.Role;

@Role("admin")
class AdminService {}
~~~

Thứ tự các phần chính trong một tệp Java là: khai báo **package** (nếu có), các dòng **import**, rồi đến khai báo class/interface/annotation/enum. Không viết **import @Role;**; ký hiệu @ chỉ xuất hiện khi gắn annotation hoặc trong từ khóa khai báo **@interface**.

Có các trường hợp thường gặp:

- **Cùng package:** Nếu lớp sử dụng và kiểu annotation nằm trong cùng package, có thể dùng tên ngắn trực tiếp mà không cần import riêng.
- **Khác package:** Dùng **import com.example.annotations.Role;** hoặc viết **@com.example.annotations.Role** tại vị trí sử dụng.
- **Wildcard import:** **import com.example.annotations.*;** cũng cho phép tìm các kiểu phù hợp trong package đó, nhưng dễ che khuất sự phụ thuộc thực tế và không tránh được mọi xung đột tên. Trong ví dụ học tập, import trực tiếp dễ đọc hơn.
- **java.lang:** Những kiểu annotation thuộc package **java.lang** được nhìn thấy qua cơ chế import ngầm của Java, ví dụ **@Override**, **@Deprecated** và **@SuppressWarnings**.
- **Package con:** Import package cha không tự import các package con. Ví dụ, **java.lang.annotation** không được import ngầm chỉ vì **java.lang** được import ngầm.

### Annotation có sẵn của Java

~~~java
class Parent {
    public String label() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String label() {
        return "child";
    }

    @Deprecated
    public void oldMethod() {
    }
}
~~~

**@Override** và **@Deprecated** dùng tên ngắn mà không cần dòng import vì chúng thuộc **java.lang**. Trái lại, khi dùng **@Retention** và **@Target**, thông thường cần import từ **java.lang.annotation**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Role {
    String value();
}
~~~

Các tên **Retention** và **Target** là kiểu annotation; **RetentionPolicy** và **ElementType** là kiểu enum; **RUNTIME** và **TYPE** là các hằng enum được tham chiếu thông qua tên enum. Đây là các thành phần khác nhau dù thường xuất hiện trong cùng một khai báo.

Nếu không muốn import các kiểu trên, có thể viết tên đầy đủ:

~~~java
@java.lang.annotation.Retention(
        java.lang.annotation.RetentionPolicy.RUNTIME)
@java.lang.annotation.Target(
        java.lang.annotation.ElementType.TYPE)
public @interface Role {
    String value();
}
~~~

Đây là ví dụ về **các cách viết tương đương cho cùng kiểu Java**, không phải hai chính sách retention/target khác nhau. Nếu dùng import tĩnh, có thể import riêng hằng enum, chẳng hạn **import static java.lang.annotation.RetentionPolicy.RUNTIME;**, rồi viết **@Retention(RUNTIME)**. Import tĩnh ấy dùng cho hằng RUNTIME; bản thân kiểu Retention vẫn cần được phân giải qua tên hoặc import thích hợp.

## 4. Ví dụ Java 17+ hoàn chỉnh: import và tên đầy đủ cùng hoạt động

Tạo cấu trúc tệp:

~~~text
src/
└── com/
    └── example/
        ├── annotations/
        │   └── Role.java
        └── app/
            └── Main.java
~~~

**Tệp src/com/example/annotations/Role.java**

~~~java
package com.example.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Role {
    String value();
}
~~~

- **@Retention(RetentionPolicy.RUNTIME)** giữ annotation tại runtime, nhờ vậy chương trình có thể đọc nó bằng reflection.
- **@Target(ElementType.TYPE)** cho phép dùng annotation lên khai báo kiểu như class.
- Kiểu public Role được đặt đúng tệp Role.java và đúng package đã khai báo.

**Tệp src/com/example/app/Main.java**

~~~java
package com.example.app;

import com.example.annotations.Role;

@Role("admin")
class ImportedService {
}

@com.example.annotations.Role("guest")
class QualifiedService {
}

public class Main {
    public static void main(String[] args) {
        printRole(ImportedService.class);
        printRole(QualifiedService.class);
    }

    private static void printRole(Class<?> type) {
        Role annotation = type.getAnnotation(Role.class);
        System.out.println(type.getSimpleName() + ": " + annotation.value());
    }
}
~~~

Biên dịch cả hai tệp từ thư mục chứa **src**:

~~~bash
javac -encoding UTF-8 -d out src/com/example/annotations/Role.java src/com/example/app/Main.java
java -cp out com.example.app.Main
~~~

Kết quả chuẩn trên stdout:

~~~text
ImportedService: admin
QualifiedService: guest
~~~

Giải thích cơ chế:

1. Khi biên dịch, trình biên dịch phân giải **@Role** nhờ dòng import và **@com.example.annotations.Role** từ tên đầy đủ. Cả hai cùng trỏ đến kiểu **com.example.annotations.Role**.
2. Lệnh **javac -d out** ghi các tệp class theo cấu trúc package; **java -cp out com.example.app.Main** dùng tên đầy đủ của class có phương thức main để chạy.
3. **Role.class** là đối tượng Class đại diện cho kiểu annotation Role. **getAnnotation(Role.class)** yêu cầu reflection tìm annotation có kiểu này trên từng class.
4. Phương thức **annotation.value()** đọc giá trị đã khai báo. Việc đọc được ở runtime là do chính Role có retention **RUNTIME**; tên ngắn hay tên đầy đủ không quyết định retention.

Vì cả hai class đều có Role, biến annotation trong ví dụ không null. Với một class không được gắn Role, **getAnnotation(Role.class)** có thể trả về null và chương trình thực tế phải kiểm tra trước khi gọi **value()**.

Ví dụ cũng cho thấy việc gắn annotation tự định nghĩa chưa tự tạo ra hành vi nghiệp vụ nào. Một trình biên dịch, annotation processor, framework hoặc mã ứng dụng cần diễn giải metadata đó. Trong chương trình trên, mã reflection chính là nơi tiêu thụ metadata.

## 5. Phân giải tên và xung đột

Việc viết tên ngắn chỉ an toàn khi nó xác định được đúng kiểu trong ngữ cảnh biên dịch:

- Nếu mã nguồn không import Role, không có Role trong cùng phạm vi và cũng không sử dụng tên đầy đủ, tham chiếu **@Role** sẽ không phân giải được kiểu; biên dịch thất bại.
- Nếu các thư viện có kiểu annotation cùng tên ngắn, ví dụ **com.example.auth.Role** và **com.example.ui.Role**, có thể dùng tên đầy đủ tại chỗ để chỉ rõ kiểu muốn gắn. Không khai báo hai **single-type import** có cùng tên ngắn trong cùng compilation unit rồi kỳ vọng Java tự chọn.
- Nếu đã biết rõ kiểu cần dùng, dạng **@com.example.auth.Role** có ý nghĩa độc lập với một import tên ngắn khác. Java vẫn cần tìm được kiểu đó trên source path, module path hoặc classpath phù hợp.
- Tên package và kiểu có phân biệt hoa/thường. **@Role** khác **@role**, và **com.example.annotations.Role** khác **com.example.annotation.Role**.
- Viết tên đầy đủ không giải quyết được việc thiếu dependency hoặc khai báo package sai. Trình biên dịch vẫn phải có quyền truy cập tới kiểu annotation.

Ở đây **@Role** là cách sử dụng, còn **Role.class** và **Role annotation** là các cách tham chiếu tới cùng một kiểu trong biểu thức hoặc khai báo biến. Không viết **@Role.class** để gắn annotation.

## 6. Các lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Viết **@Role** ở package khác nhưng không import | Tên Role chưa được phân giải | Thêm **import com.example.annotations.Role;** hoặc dùng **@com.example.annotations.Role** |
| Viết **import @Role;** | Import chỉ nhận tên kiểu/package theo cú pháp Java | Viết **import com.example.annotations.Role;** |
| Viết **@java.lang.annotation.* ** | Wildcard chỉ hợp lệ trong khai báo import, không phải tên kiểu tại vị trí sử dụng | Dùng tên kiểu cụ thể, ví dụ **@java.lang.annotation.Retention(...)** |
| Tưởng **import java.lang.*;** bao gồm Retention | Import không lan xuống package con | Import từ **java.lang.annotation** hoặc dùng tên đầy đủ |
| Đặt **public @interface Role** trong tệp tên khác | Tên tệp không phù hợp với top-level public type | Đặt vào **Role.java** |
| Viết **@Role** nhưng phần tử **value()** bắt buộc | Chưa cung cấp giá trị cho annotation element không có default | Dùng **@Role("admin")** hoặc **@Role(value = "admin")** |
| Dùng Role lên vị trí trái **@Target** | Annotation không cho phép gắn lên vị trí đó | Xem khai báo **@Target** và gắn đúng vị trí |
| Không đọc thấy annotation qua reflection | Retention không phải RUNTIME hoặc đọc sai phần tử | Kiểm tra **@Retention(RUNTIME)**, đúng kiểu và đúng đối tượng phản chiếu |

Lưu ý trong bảng: **@Target** và **@Retention** là metadata về quy tắc áp dụng và khả năng tồn tại của annotation; import và tên đầy đủ chỉ giúp **tham chiếu đúng kiểu**. Hai khía cạnh này cần được kiểm tra riêng.

## 7. Tự kiểm tra kiến thức

**Tình huống A.** Có khai báo **public @interface Trace {}** trong package **org.example.meta**. Class trong package **org.example.service** muốn sử dụng Trace. Hai cách đúng là:

~~~java
import org.example.meta.Trace;

@Trace
class OrderService {}
~~~

Hoặc không import và dùng tên đầy đủ:

~~~java
@org.example.meta.Trace
class OrderService {}
~~~

**Tình huống B.** Tại sao **@Override** thường không cần import, còn **@Target** lại cần? Vì Override thuộc package **java.lang**, được import ngầm; Target thuộc **java.lang.annotation**, là package riêng.

**Tình huống C.** Đổi **@Role("admin")** thành **@com.example.annotations.Role("admin")** có làm đổi dữ liệu reflection đọc được không? Không, nếu hai tên phân giải tới cùng một kiểu Role và mọi khai báo khác giữ nguyên.

Khi đọc một annotation bất kỳ, hãy xác định theo thứ tự: **tên kiểu sau @ là gì → kiểu thuộc package nào → mã nguồn nhìn thấy kiểu đó nhờ cùng package/import/tên đầy đủ hay chưa → @Target có cho phép vị trí sử dụng không → metadata có được giữ tới giai đoạn cần sử dụng không**. Chuỗi kiểm tra này giúp tách lỗi về tên/import ra khỏi lỗi áp dụng hoặc xử lý annotation.
