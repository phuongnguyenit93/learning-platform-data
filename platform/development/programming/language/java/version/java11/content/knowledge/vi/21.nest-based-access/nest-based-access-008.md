# Phân biệt cơ chế JVM với quy tắc truy cập ngôn ngữ — Nest-based access trong Java 11+

## 1. Bài toán và kết luận quan trọng

Từ **Java 11**, **JEP 181 — Nest-Based Access Control** cho phép các class/interface thuộc **cùng một nest (nestmates)** truy cập trực tiếp các member `private` của nhau ở **cấp JVM**. Đây là thay đổi trong **quy tắc kiểm tra truy cập khi liên kết/thực thi bytecode**, không phải một cú pháp mới và **không nới rộng quy tắc `private` của ngôn ngữ Java**.

Trong mã nguồn Java, việc một nested class đọc được `private` của outer class hoặc một nested sibling đã hợp lệ từ lâu. JDK 11 đưa cách JVM kiểm tra quyền gần với khái niệm lồng nhau mà Java source đã có, nên `javac` không còn cần sinh các phương thức truy cập tổng hợp cho nhiều trường hợp như trước.

Cần nhớ ba tầng **khác nhau**:

1. **Java source/JLS:** `javac` xét một biểu thức truy cập có hợp lệ theo phạm vi khai báo, tên, modifier, kiểu và quy tắc của ngôn ngữ hay không.
2. **Classfile/JVMS:** `javac` ghi các classfile riêng biệt, có thể có attribute `NestHost` và `NestMembers` để mô tả nest.
3. **JVM runtime:** khi liên kết/thực hiện tham chiếu tới member `private`, JVM kiểm tra caller có thuộc **cùng nest hợp lệ** với class khai báo member không.

**Không được hiểu** “Java 11 cho phép bất kỳ hai class cùng package truy cập private của nhau”. Cũng **không được hiểu** “JVM kiểm tra được nestmates nên mọi cách viết biểu thức Java source đều hợp lệ”.

Bài sử dụng quy tắc **Java 11 vẫn áp dụng trên JDK hiện đại**; ví dụ được biên dịch bằng `javac --release 11`, có trường hợp **biên dịch thành công** và **một trường hợp cố ý phải bị từ chối**.

## 2. Quy tắc truy cập ở tầng Java language: JLS 6.6.1

Trong Java, access modifier của một member ảnh hưởng tới **vị trí có thể sử dụng member trong source**. Theo **Java Language Specification (JLS) `6.6.1**, `private` có thể được truy cập trong **thân của top-level type bao quanh nơi khai báo member**. Điều đó bao gồm mã của các nested types nằm trong top-level type ấy.

Bảng khái quát:

| Modifier của member | Quy tắc Java source (khái quát) | Nest-based access làm thay đổi? |
| --- | --- | --- |
| `public` | Có thể truy cập nếu type, module và các điều kiện liên quan cho phép | Không |
| `protected` | Quy tắc cùng package hoặc subclass, với ràng buộc ngữ cảnh truy cập | Không |
| *package-private* (không ghi modifier) | Truy cập từ cùng package khi đủ điều kiện | Không |
| `private` | Truy cập trong thân **top-level type bao quanh khai báo** | **Không đổi ở source** |

Lưu ý: JLS còn có quy định cụ thể cho subtype, kiểu lồng nhau, protected access, name resolution, generic types và module. Bảng chỉ nêu phạm vi cốt lõi, không thay thế toàn bộ JLS.

### 2.1. Outer class, nested class và sibling nested class

Mã Java này **hợp lệ**:

```java
public class Container {
    static class Secret {
        private final int number = 7;

        private int doubled() {
            return number * 2;
        }
    }

    static class Reader {
        static int read(Secret secret) {
            return secret.number;      // Hợp lệ.
        }

        static int calculate(Secret secret) {
            return secret.doubled();   // Hợp lệ.
        }
    }
}
```

Cả `Container.Secret` và `Container.Reader` nằm trong **cùng top-level type `Container`**, nên theo **JLS** biểu thức truy cập là hợp lệ. Điều này không đòi `Reader` phải kế thừa `Secret`; hai class có quan hệ **nesting**, không phải quan hệ **inheritance**.

Nếu outer class khai báo một private field, nested class có thể dùng field ấy khi có đúng instance hoặc khi field là static. Nếu nested class khai báo private constructor/method/field, mã khác bên trong cùng top-level type cũng có thể tham chiếu theo quy tắc tương ứng.

### 2.2. Hai top-level classes cùng package vẫn không có quyền private

Ví dụ sau **cố ý sai** (không dùng làm mã chạy thành công):

```java
package demo;

class Alpha {
    private int secret = 42;
}

class Beta {
    int read(Alpha alpha) {
        return alpha.secret; // LỖI BIÊN DỊCH: private access.
    }
}
```

`Alpha` và `Beta` có thể cùng package, thậm chí cùng **một file `.java`**, nhưng **không** cùng thân top-level type. Theo JLS, `Beta` không được truy cập `Alpha.secret`.

`package-private` là mức truy cập khác với `private`. Nếu cần công khai chức năng giữa hai top-level classes cùng package, hãy thiết kế API/phương thức thích hợp hoặc cân nhắc package-private khi đúng yêu cầu đóng gói; **đừng dựa vào Nest-based access để phá private**.

### 2.3. Subclass không tự có quyền private của superclass

```java
class Parent {
    private int secret = 42;
}

class Child extends Parent {
    int read() {
        // return secret; // Không hợp lệ: private không được kế thừa.
        return 0;
    }
}
```

Đây là mảnh mã minh họa; dòng sai đã comment. Một subclass **không phải nestmate chỉ vì extends**. Java vẫn yêu cầu dùng API truy cập do superclass chủ động cung cấp, hoặc code phải nằm trong phạm vi lồng nhau hợp lệ theo JLS. Không nhầm `private` với `protected`.

## 3. JVM làm gì khác từ Java 11?

Mỗi nested class trong Java được biên dịch thành classfile riêng, chẳng hạn:

```text
Container.class
Container$Secret.class
Container$Reader.class
```

JVM làm việc với các classfile riêng biệt. Trước cơ chế nestmates, truy cập trực tiếp `private` giữa hai classfile tách biệt không được JVMS cho phép; compiler thường tạo **synthetic accessor** (chẳng hạn phương thức trợ giúp có tên dạng `access$...`) để chương trình Java source hợp lệ vẫn chạy được.

Từ **JEP 181 trong Java 11**, JVM công nhận một **nest**: nhóm class/interface có quyền truy cập qua lại vào member `private` của nhau, miễn metadata và các điều kiện runtime hợp lệ. `javac` có thể biên dịch truy cập trực tiếp đến private field/method/constructor, không cần nới modifier hay thêm một accessor trung gian chỉ vì classfile được tách ra.

### 3.1. Nest host và nest members

Một **nest host** là class/interface đứng tên quản lý một nest. Những thành viên khác gọi là **nest members**.

Trong classfile version **55.0** (Java 11), hai attribute quan trọng là:

| Classfile attribute | Đặt trên class nào? | Vai trò |
| --- | --- | --- |
| `NestMembers` | Nest host | Liệt kê các class/interface mà host cho phép tham gia nest |
| `NestHost` | Nest member không phải host | Chỉ ra class/interface host của mình |

Ví dụ:

```text
NestAccessDemo.class
  NestMembers:
    NestAccessDemo$Vault
    NestAccessDemo$Reader

NestAccessDemo$Vault.class
  NestHost: class NestAccessDemo

NestAccessDemo$Reader.class
  NestHost: class NestAccessDemo
```

Tên và quan hệ trên phù hợp chương trình kiểm thử ở mục 7. Attribute `NestMembers` và `NestHost` cần **khớp nhau** theo quy tắc JVMS. Không thể tùy tiện sửa một classfile để tự xưng là member của nest thuộc class khác mà không được host công nhận.

**`InnerClasses` không thay thế `NestHost/NestMembers`:** `InnerClasses` chủ yếu mô tả cấu trúc type lồng nhau cho classfile và các công cụ; quyền truy cập `private` theo nest ở JVM phải dựa trên kiểm tra nest hợp lệ. `EnclosingMethod` cũng là metadata về ngữ cảnh local/anonymous class, không phải giấy phép tự do gọi mọi private member.

### 3.2. JVM kiểm tra quyền ở đâu?

Theo **Java Virtual Machine Specification (JVMS) `5.4.4 — Access Control**, trong quá trình resolution/linking của một tham chiếu tới class, field hoặc method, JVM kiểm tra xem caller được truy cập target hay không.

Với member `private`, điều kiện JVM quan tâm là caller cùng **nest** với class/interface khai báo member. Cùng tên package **chưa đủ**. Một nest cần thỏa mãn kiểm tra **runtime package**, **nest host** và khai báo membership.

Không nên nói JVM “bỏ toàn bộ kiểm tra private” sau Java 11. Thực tế JVM **thay đổi điều kiện được phép truy cập private** từ cùng class riêng lẻ thành cùng **nest hợp lệ**.

### 3.3. Runtime package không đơn giản là cùng dòng package

Trong JVMS, một **runtime package** gắn với **tên package và defining class loader**. Nếu hai class có cùng dòng `package demo;` nhưng được định nghĩa bởi hai class loaders khác nhau, chúng **không mặc nhiên** thuộc cùng runtime package. Nestmates phải đáp ứng giới hạn runtime package và metadata tương ứng; các class liên quan thường cùng loader và cùng runtime module.

Vì runtime package được gắn với một runtime module, nest-based access không phải cơ chế để vượt **module boundaries**. `module-info.java`, exports/opens và các quy tắc module vẫn có vai trò riêng. Đừng dùng quyền cùng nest như lý do bỏ kiểm soát class loader, module hoặc đối tác tải mã.

### 3.4. Nếu metadata không hợp lệ hoặc thiếu?

Một classfile không khai báo `NestHost` thường là **host của chính nó**; nếu cũng không liệt kê `NestMembers` thì tạo một **singleton nest** gồm đúng class đó.

Nếu classfile khai báo nest sai, host không công nhận member hoặc có runtime package không phù hợp, việc kiểm tra có thể gặp **`IncompatibleClassChangeError`**. Nếu caller không có quyền truy cập target member, JVM có thể báo **`IllegalAccessError`**. Những lỗi này xảy ra ở **tầng liên kết/thực thi bytecode**, khác với thông báo compile-time “`private has private access`” do `javac` phát hiện trong source.

Không cam kết một classfile lỗi bất kỳ luôn phát đúng một loại exception trước tất cả thao tác; thứ tự resolution, loading và validation cũng quan trọng.

## 4. So sánh ba lớp kiểm soát: compiler, JVM và reflection

| Câu hỏi | Java source/compiler | JVM/runtime | Reflection/Method Handles |
| --- | --- | --- | --- |
| Ai quyết định? | `javac` theo JLS | JVM theo JVMS/classfile metadata | API reflection/lookup và các quy tắc truy cập liên quan |
| Tầng kiểm tra | Khi biên dịch source | Khi load/link/resolve/thực thi tham chiếu | Khi tra cứu/đọc/gọi thành viên theo API |
| Nestmates có ý nghĩa? | Source Java lồng nhau đã có quyền lexical theo JLS | JVM Java 11 cho phép **private trực tiếp giữa nestmates hợp lệ** | API có thể xét nestmates, đồng thời áp dụng các kiểm tra riêng |
| Hai top-level classes cùng package? | Không đọc private của nhau | Không là nestmates chỉ vì package | Không tự được quyền private |
| Class khác module? | Phải theo quy tắc type/module | Phải theo quy tắc runtime/package/module | Có thêm điều kiện lookup, export/open và accessibility |
| Lỗi thường thấy | Compile-time error | `IllegalAccessError`/`IncompatibleClassChangeError` khi có vấn đề tương ứng | `IllegalAccessException`/`InaccessibleObjectException` hoặc lỗi lookup thích hợp |

### 4.1. Class.getNestHost, getNestMembers, isNestmateOf

Từ **Java 11**, `java.lang.Class` cung cấp:

```java
Class<?> host = SomeClass.class.getNestHost();
Class<?>[] members = SomeClass.class.getNestMembers();
boolean same = A.class.isNestmateOf(B.class);
```

Đây là các **API quan sát quan hệ nest**, không phải API yêu cầu JVM “cấp quyền private” cho bất kỳ class nào.

- `getNestHost()` trả host của nest hiện tại; với singleton nest, trả chính class đó.
- `getNestMembers()` trả mảng thành viên. **Host ở vị trí 0**, thứ tự các thành viên còn lại **không được bảo đảm**; nếu cần output ổn định thì sort trước khi in.
- `isNestmateOf(other)` trả `true` nếu hai class/interface thuộc cùng nest (bao gồm class với chính nó). Không tự suy ra từ tên file hoặc prefix `$`.

**Cẩn thận:** `getNestMembers()` không đồng nghĩa với `getDeclaredClasses()`; đây là hai câu hỏi khác nhau. API nest phản ánh nhóm truy cập JVM, có thể có cả những type do compiler tạo cho các cấu trúc lồng nhau; `getDeclaredClasses()` chủ yếu phản ánh member classes/interfaces được khai báo trong class. Đừng kết luận một class là nestmate chỉ vì tên binary của nó chứa `$`.

Với array, primitive và `void`, Javadoc Java 11 mô tả việc trả về singleton nest tương ứng. Trong các trường hợp classfile lỗi hoặc class không thể load, một số API introspection có thể báo lỗi theo Javadoc; ví dụ thực hành ở mục 7 dùng các classfile hợp lệ.

### 4.2. Nest-based access không cho gọi setAccessible tùy ý

Java reflection (chẳng hạn `Field`, `Method`, `Constructor`), `MethodHandles.Lookup` và Java Platform Module System có **các quy tắc riêng** về người gọi, quyền truy cập và mở package.

Ví dụ:

```java
Field field = A.class.getDeclaredField("secret");
// field.setAccessible(true); // Không giả định luôn thành công.
```

Đây là mảnh mã giải thích, cần import `java.lang.reflect.Field` và có một class `A` thích hợp. `setAccessible(true)` không phải quyền mặc định của mọi caller: Java modules và các giới hạn reflective access có thể từ chối, chẳng hạn bằng `InaccessibleObjectException`. Đừng vô hiệu hóa encapsulation của module chỉ để đọc private trong ứng dụng sản xuất.

`MethodHandles.privateLookupIn(...)` cũng cần caller có quyền lookup thích hợp và tuân thủ ranh giới module. **JEP 181 không cung cấp phép thuật để arbitrary code biến thành nestmate** hoặc bỏ qua các bước xác thực của API reflection.

### 4.3. Phân biệt khả năng bytecode với tính hợp lệ Java source

Ở **tầng JVM**, những classfile có metadata nest hợp lệ được phép truy cập private giữa nestmates. Đặc tả bytecode không đòi chúng phải được tạo bằng chính `javac`.

Ở **tầng Java source**, `javac` vẫn tuân thủ JLS: một class top-level không được trực tiếp đọc private của một class top-level độc lập chỉ vì muốn “xếp chung nest”. Việc dùng công cụ tạo bytecode để mô tả một nest không có sẵn trong cú pháp Java **không mở rộng JLS** và không phải hướng thiết kế API được khuyến nghị.

## 5. Vì sao JEP 181 hữu ích dù không thêm cú pháp mới?

Nest-based access giải quyết một khoảng cách giữa **ngôn ngữ** và **cách compiler xuất bytecode**:

```text
Quy tắc Java source:
  Container.Reader hợp lệ khi đọc private của Container.Secret
                  │
                  ▼
javac --release 11:
  Container.class
  Container$Reader.class   + NestHost: Container
  Container$Secret.class   + NestHost: Container
  Container.class          + NestMembers: Reader, Secret
                  │
                  ▼
JVM:
  Kiểm tra hai class cùng nest hợp lệ
  Cho phép getfield/invoke... private trực tiếp
```

**Lợi ích quan trọng:**

- Giảm nhu cầu compiler sinh các phương thức tổng hợp dùng để bắc cầu giữa classfiles thuộc cùng một cấu trúc source.
- Giữ member ở modifier `private` trong classfile, đồng thời JVM có thể thực hiện truy cập hợp lệ giữa nestmates.
- Hỗ trợ mô hình kiểm tra quyền nhất quán hơn cho core reflection và method handles trong các ngữ cảnh nestmate.
- Hữu ích cho các công cụ phân tích bytecode, thư viện tạo code và việc hiểu kết quả `javap`.

**Không làm thay đổi:**

- Ý nghĩa của `public`, `protected`, *package-private* và `private` trong Java source.
- Cách `private` không được kế thừa.
- Khả năng một class top-level cùng package truy cập private class khác.
- Quy tắc phân giải method, kiểu, module và class-loader boundaries ngoài phạm vi nest.
- Bảo mật dữ liệu nghiệp vụ, authentication, access control ở cấp dịch vụ.

Một chương trình Java thông thường **không cần gọi API nest** để có quyền truy cập vốn đã hợp lệ; compiler và JVM xử lý cơ chế này. `getNestHost()`/`getNestMembers()` là công cụ introspection/diagnostic khi cần hiểu classfile.

## 6. Ví dụ Java 11: nested siblings truy cập private trực tiếp

Tạo tệp **`NestAccessDemo.java`**. Chương trình có:

- `NestAccessDemo`: **top-level host**.
- `Vault`: static nested class có **private constructor**, **private field** và **private method**.
- `Reader`: static nested sibling, dùng trực tiếp cả ba private member của `Vault`.
- `Outside`: một **top-level class khác trong cùng compilation unit/package**, không phải nestmate.

Để đầu ra ổn định, chương trình sort tên từ `getNestMembers()`; không dựa vào thứ tự thành viên sau host.

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class NestAccessDemo {
    static class Vault {
        private final int code;

        private Vault(int code) {
            this.code = code;
        }

        private String label() {
            return "vault:" + code;
        }
    }

    static class Reader {
        static Vault create(int code) {
            return new Vault(code);  // Private constructor của sibling.
        }

        static int read(Vault v) {
            return v.code;           // Private field của sibling.
        }

        static String describe(Vault v) {
            return v.label();        // Private method của sibling.
        }
    }

    public static void main(String[] args) {
        Vault vault = Reader.create(42);
        boolean same = Vault.class.isNestmateOf(Reader.class);
        boolean external = Vault.class.isNestmateOf(Outside.class);

        if (!same || external
                || Reader.read(vault) != 42
                || !Reader.describe(vault).equals("vault:42")
                || Vault.class.getNestHost() != NestAccessDemo.class) {
            throw new AssertionError("Nest access validation failed");
        }

        String names = Arrays.stream(
                NestAccessDemo.class.getNestMembers())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", "));

        System.out.println("nest host = "
                + Vault.class.getNestHost().getSimpleName());
        System.out.println("nest members = [" + names + "]");
        System.out.println("siblings = " + same);
        System.out.println("same-package top-level nestmate = "
                + external);
        System.out.println("private constructor = "
                + (vault != null));
        System.out.println("private field = "
                + Reader.read(vault));
        System.out.println("private method = "
                + Reader.describe(vault));
        System.out.println("ALL CHECKS PASSED");
    }
}

class Outside {
    // Cùng package/compilation unit nhưng không nằm trong NestAccessDemo.
}
```

Chạy trong thư mục chứa tệp:

```bash
javac --release 11 NestAccessDemo.java
java NestAccessDemo
```

**Đầu ra đã biên dịch/chạy kiểm chứng:**

```text
nest host = NestAccessDemo
nest members = [NestAccessDemo, Reader, Vault]
siblings = true
same-package top-level nestmate = false
private constructor = true
private field = 42
private method = vault:42
ALL CHECKS PASSED
```

### 6.1. Vì sao mỗi dòng đúng?

- `nest host = NestAccessDemo`: class `Vault` được ghi là member của nest do outer top-level class `NestAccessDemo` làm host.
- `nest members = [...]`: host và hai nested class thuộc cùng nest. Danh sách được **sort** để không giả định thứ tự không được đặc tả.
- `siblings = true`: `Vault.class.isNestmateOf(Reader.class)` trả true.
- `same-package top-level nestmate = false`: `Outside` không phải nested member của `NestAccessDemo`, dù cùng file nguồn và cùng package mặc định.
- `private constructor = true`: `Reader.create` gọi thành công `new Vault(code)` dù constructor `private`.
- `private field = 42`: `Reader` truy cập trực tiếp `v.code`.
- `private method = vault:42`: `Reader` gọi trực tiếp `v.label()`.
- `ALL CHECKS PASSED`: chương trình kiểm tra quan hệ nest và dữ liệu, không dựa vào một output “trông có vẻ đúng”.

### 6.2. Xem bytecode bằng javap

Sau khi `javac --release 11` tạo classfiles, chạy:

```bash
javap -v -p NestAccessDemo
javap -v -p 'NestAccessDemo$Reader'
javap -v -p 'NestAccessDemo$Vault'
```

Đây là các lệnh đọc classfile; dấu nháy đơn quanh tên chứa `$` tránh shell mở rộng biến trong một số môi trường. `javap` có trong JDK.

Trong kết quả đã kiểm chứng:

```text
major version: 55
...
NestHost: class NestAccessDemo
```

Lệnh trên `NestAccessDemo$Reader` cho thấy **classfile major version 55** và `NestHost`. Classfile của host ghi `NestMembers` để liệt kê hai member.

Ở phần bytecode của `Reader`, có các tham chiếu **trực tiếp** như:

```text
invokespecial ... // Method NestAccessDemo$Vault."<init>":(I)V
getfield      ... // Field NestAccessDemo$Vault.code:I
invokevirtual ... // Method NestAccessDemo$Vault.label:()Ljava/lang/String;
```

Dấu `...` chỉ là vị trí index/offset mà `javap` in, có thể khác tùy compiler; không phải phần bắt buộc của cú pháp bytecode. Điểm cốt lõi là các instruction này truy cập **member `private` của classfile khác trong cùng nest**, không phải gọi một accessor tổng hợp `access$...` do compiler tự tạo.

**Không nhầm phiên bản classfile và phiên bản Java runtime:** `--release 11` yêu cầu cú pháp/API và classfile compatible Java 11, nhưng bạn vẫn có thể chạy kết quả trên một JDK mới hơn.

## 7. Thử sai có chủ đích: top-level class cùng package bị từ chối

Giữ nguyên classfiles đã biên dịch ở mục 6. Tạo file riêng **`DeniedSamePackage.java`** cạnh `NestAccessDemo.java`:

```java
public class DeniedSamePackage {
    public static void main(String[] args) {
        System.out.println(
                NestAccessDemo.Reader.create(5).code);
        // CỐ Ý SAI: Vault.code là private.
    }
}
```

Chạy:

```bash
javac --release 11 -cp . DeniedSamePackage.java
```

**Kết quả mong đợi: biên dịch THẤT BẠI** vì `code` có `private access` trong `Vault`. Thông điệp cụ thể có thể khác tùy JDK và ngôn ngữ hệ thống; không nên hardcode số dòng/thông báo đầy đủ thành một golden output.

Trường hợp này đã được kiểm chứng trong môi trường thử: `javac` trả exit code khác 0, phần chẩn đoán có cụm `private access`. Đây là **lỗi quy tắc Java source**, không phải `IllegalAccessError` runtime. File được thiết kế **không biên dịch được**, do đó đừng thêm nó vào lệnh biên dịch của chương trình chạy thành công ở mục 6.

### 7.1. Nếu muốn được truy cập thì làm cách nào?

Chọn một **thiết kế source hợp lệ**, tùy yêu cầu đóng gói:

1. Đưa logic phối hợp vào một nested class cùng top-level type nếu thật sự là thành phần nội bộ của cùng abstraction.
2. Cung cấp một phương thức `public` hoặc *package-private* có kiểm tra/điều kiện phù hợp, thay vì lộ trực tiếp private field.
3. Sử dụng một API interface hoặc service theo trách nhiệm nghiệp vụ; không tự sửa classfile attribute để “mở private”.

Nest-based access là hỗ trợ compiler/JVM cho code hợp lệ, **không** là thiết kế ủy quyền tài nguyên cho người gọi tùy ý.

## 8. Những điểm dễ nhầm về nested types, classfile và JVM

### 8.1. Nested source không nhất thiết là kế thừa

Một `static nested class`, một inner class, một local class hoặc anonymous class có quan hệ lồng nhau với top-level type; chúng không trở thành subclass của outer class chỉ vì được khai báo bên trong.

Một `class Child extends Parent` ở cùng package lại có quan hệ kế thừa, không tự thuộc nest của `Parent`. Nest là một **quan hệ metadata/cấu trúc truy cập**, khác với superclass chain.

### 8.2. Cùng binary name prefix không đủ

Tên `Outer$Inner` là một quy ước classfile của nested classes Java và có thể được các công cụ tạo bytecode sử dụng. **JVM không xác minh nestmates chỉ bằng phép kiểm tra prefix tên**. Phải có host/member attributes đúng, cùng runtime package và validation cần thiết.

### 8.3. Cùng source file cũng chưa đủ

Trong cùng file có thể khai báo một `public class Main` và thêm nhiều top-level classes package-private. Những top-level classes độc lập ấy **không mặc nhiên thuộc nest của `Main`**. Ví dụ `Outside` và `DeniedSamePackage` chứng minh điều này.

### 8.4. Chỉ xem InnerClasses chưa đủ

`javap -v` có thể in `InnerClasses`, `NestHost` và `NestMembers` cùng lúc. `InnerClasses` giúp mô tả cấu trúc khai báo; **nest access ở JVM** dựa trên quan hệ host/member có điều kiện, không phải chỉ dựa vào việc type có dấu `$` hoặc có ghi `InnerClasses`.

### 8.5. Không phải “private được kế thừa” sau Java 11

`private` không được kế thừa như một member accessible thông thường. Nested sibling có thể gọi member private vì **quy tắc bao quanh lexical của JLS** và cơ chế nestmate của JVM, không phải vì extends.

### 8.6. Reflection vẫn có ranh giới

`Class.isNestmateOf` là introspection, không tự sửa quyền của `Field` hoặc `Method`. Việc gọi `setAccessible(true)`, `MethodHandles.privateLookupIn` hay truy cập module không thuộc quyền mặc định của bất kỳ caller nào. Luôn tôn trọng encapsulation và module boundaries.

### 8.7. Classloader khác nhau có thể làm nest mất hiệu lực

Cùng source package name nhưng **defining class loaders khác nhau** có thể tạo các runtime package riêng biệt, nên metadata không còn tạo được nest hợp lệ giữa chúng. Với ứng dụng plugin/agent/classloader tùy biến, cần đặc biệt chú ý các lỗi linkage và class identity, thay vì giả định tên class giống nhau luôn là cùng class.

## 9. Lỗi thường gặp và cách phân biệt

| Triệu chứng | Lớp phát hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- | --- |
| `javac: ... has private access` | Java source/compiler | Truy cập từ một top-level type độc lập | Sửa source/access API/lexical nesting |
| `IllegalAccessError` khi chạy classfile | JVM resolution/access | Caller không được phép truy cập member, nest không khớp hoặc binary khác dự tính | Kiểm tra classfile, runtime class, phương thức bị gọi và nest metadata |
| `IncompatibleClassChangeError` liên quan nest | JVM nest validation | Host/member khai báo không nhất quán hoặc sai runtime package | Biên dịch lại đồng bộ classfiles; kiểm tra classloader/shading |
| `NoClassDefFoundError` | JVM loading/resolution | Thiếu class hoặc lỗi khi resolve nest host/member | Kiểm tra deployment, classpath/modulepath/classloader |
| `getNestMembers` trả thiếu/khác kỳ vọng | Introspection | Classfile version, host/member metadata hoặc loại class khác dự tính | Xem `javap -v`, phân biệt member classes và nest members |
| `getNestMembers` thứ tự khác | Introspection | Thứ tự sau host không được bảo đảm | Sort trước khi so sánh/hiển thị |
| `isNestmateOf` false dù cùng package | JVM/Class API | Cùng package không đồng nghĩa cùng nest | Kiểm tra host và các attribute |
| `access$...` xuất hiện trong binary cũ | Compiler/classfile thế hệ trước | Có thể là synthetic accessor cho nested private access | Hiểu lịch sử tạo bytecode; không phải API ứng dụng |
| Reflection bị từ chối | Reflection/module | Member visibility, lookup quyền, package không mở | Dùng API đúng quyền, tránh mở module tùy tiện |
| “Class A.class == B.class” sai dù cùng tên | Classloader | Class identity bao gồm defining loader | Kiểm tra loader và runtime package |
| Sửa bytecode NestHost một phía không chạy | JVMS validation | Member tự khai báo host nhưng host không công nhận | Không tự tạo nest sai metadata; dùng compiler/toolchain đúng |
| Kiểu/field không thể truy cập dù cùng nest | JLS/JVMS khác điều kiện | Type accessibility, name resolution, module hoặc constraint khác | Xác định lỗi đang ở compile-time hay runtime |

## 10. Tự kiểm tra kiến thức

**Câu 1.** Java 11 có cho hai top-level classes cùng package đọc `private` của nhau không?  
**Đáp án:** Không. Trong Java source, `private` vẫn tuân theo phạm vi body của top-level type bao quanh khai báo; same package không đủ.

**Câu 2.** `Container.Reader` là sibling của `Container.Vault`. Reader có thể gọi `Vault.privateMethod()` không?  
**Đáp án:** Có nếu biểu thức Java hợp lệ trong cùng top-level type và type/instance tương ứng; ở JVM các classfile cần thuộc cùng nest hợp lệ.

**Câu 3.** Tại sao source đã hợp lệ từ trước Java 11 nhưng JEP 181 vẫn có ích?  
**Đáp án:** Trước đó JVM kiểm tra private ở mức classfile riêng lẻ, nên compiler thường thêm accessor trung gian. Java 11 cho phép private access trực tiếp giữa nestmates hợp lệ ở JVM, phù hợp hơn với source.

**Câu 4.** `NestHost` và `NestMembers` dùng để làm gì?  
**Đáp án:** Member ghi host ở `NestHost`; host liệt kê members trong `NestMembers`. JVM dùng chúng để xác định nhóm được phép truy cập private cùng nest.

**Câu 5.** Có thể dùng `Class.isNestmateOf` để “thêm” hai class vào một nest không?  
**Đáp án:** Không. Đây là hàm **hỏi/kiểm tra**, trả boolean; không sửa classfile hay quan hệ truy cập.

**Câu 6.** `getNestMembers()` có luôn sắp xếp các nested classes theo thứ tự khai báo trong source không?  
**Đáp án:** Không. Ngoài host ở vị trí đầu, thứ tự phần còn lại không được bảo đảm.

**Câu 7.** Tại sao một class có tên `Outer$Another` chưa chắc là nestmate của `Outer`?  
**Đáp án:** JVM không dựa vào prefix tên; nó cần metadata nest hợp lệ và các điều kiện runtime package/loader.

**Câu 8.** Một subclass của `Vault` tự động trở thành nestmate để đọc private field không?  
**Đáp án:** Không. Inheritance và nest membership là hai quan hệ khác nhau, `private` không được kế thừa thành member accessible.

**Câu 9.** Khi gặp lỗi private trong `javac` và `IllegalAccessError` ở runtime, có phải cùng một nguyên nhân không?  
**Đáp án:** Không nhất thiết. Một bên là kiểm tra JLS ở compile-time; bên kia là kiểm tra JVMS/linkage của classfiles đang chạy. Cần chẩn đoán đúng tầng.

**Câu 10.** JEP 181 có mở `private` xuyên module boundaries hoặc bỏ yêu cầu mở package cho reflection không?  
**Đáp án:** Không. Nest phải thỏa runtime package/loader và các quy tắc truy cập tương ứng; reflection/module có kiểm tra riêng.

## 11. Tổng kết

```text
JLS / javac (source)
  ├─ private hợp lệ trong body top-level type bao quanh
  ├─ nested siblings có thể truy cập nhau
  └─ hai top-level classes cùng package KHÔNG được đọc private của nhau
             |
             v
Classfiles Java 11 (major 55)
  ├─ NestHost ở member
  └─ NestMembers ở host
             |
             v
JVMS / JVM (runtime)
  ├─ xác định cùng nest hợp lệ, cùng runtime package
  ├─ kiểm tra quyền private khi resolution
  └─ cho phép private field/method/constructor trực tiếp giữa nestmates
```

**Điểm ghi nhớ quan trọng nhất:** JEP 181 mở rộng **cách JVM xác minh quyền truy cập `private` giữa các classfile có quan hệ nest**, **không thay đổi quyền truy cập `private` của chương trình nguồn Java**. Phạm vi biên dịch hợp lệ vẫn do JLS quyết định; bytecode đã biên dịch phải được JVM kiểm tra lại theo JVMS.

Để hiểu một tình huống cụ thể, hãy hỏi theo thứ tự: **source có hợp lệ theo JLS?** → **classfiles có `NestHost/NestMembers` đúng?** → **runtime package/classloader/module có khớp?** → **JVM có chấp nhận private reference tại resolution không?**

### Tài liệu chính thức còn áp dụng

- [OpenJDK — JEP 181: Nest-Based Access Control](https://openjdk.org/jeps/181)
- [Java SE 11 — JLS `6.6.1: Determining Accessibility, quy tắc private trong top-level type](https://docs.oracle.com/javase/specs/jls/se11/html/jls-6.html#jls-6.6.1)
- [Java SE 11 — JVMS `5.4.4: JVM Access Control và nestmate test](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.4)
- [Java SE 11 — JVMS `4.7.28: NestHost Attribute](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.28)
- [Java SE 11 — JVMS `4.7.29: NestMembers Attribute](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.29)
- [Java SE 11 — java.lang.Class: getNestHost/getNestMembers/isNestmateOf](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html)
- [Java SE 11 Release Notes — JEP 181 và tính tương thích ngôn ngữ](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html)
- [Java SE 25 — JVMS `5.4.4, cơ chế nestmates vẫn được đặc tả](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4.4)
