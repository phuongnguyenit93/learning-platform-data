# Nest host, nest member và nhóm lớp cùng một thực thể mã trong Java 11+

## 1. Nest-based access là gì?

Từ **Java 11**, JDK triển khai **JEP 181 — Nest-Based Access Control**. Một **nest** là một nhóm class/interface có quan hệ với nhau ở cấp JVM, thường tương ứng **một lớp hoặc interface top-level cùng các kiểu được khai báo lồng bên trong nó** trong mã nguồn Java. Các thành viên này có thể truy cập `private` field, method và constructor của nhau theo cơ chế kiểm tra truy cập của JVM.

Ví dụ:

```java
class Order {
    private String code;

    static class Validator {
        static boolean valid(Order order) {
            return order.code != null;
        }
    }
}
```

Đây là ví dụ **minh họa**, không có `main`. Trong source Java, `Order.Validator` được phép đọc `Order.code` mặc dù `code` là `private`. Java 11 giúp **bytecode và cơ chế kiểm tra quyền của JVM hiểu được quan hệ đó một cách trực tiếp**, thay vì bắt trình biên dịch tạo các phương thức truy cập trung gian chỉ để vượt ranh giới giữa các file `.class`.

**Điểm cốt lõi:** nest là **nhóm lớp cùng một thực thể mã logic** ở mức class file và JVM, không phải synonym của package, một tệp `.java` hay quan hệ kế thừa. Một top-level class có thể là nest host của những nested classes, nhưng hai top-level classes chỉ nằm chung file nguồn hoặc chung package **không mặc nhiên là nestmates**.

JEP 181 **không thay đổi quy tắc quyền truy cập của ngôn ngữ Java ở cấp source**: mã nguồn Java vốn đã cho phép outer/nested types truy cập các member riêng của nhau theo quy tắc lexical nesting. Thay đổi chính là cách JVM **biểu diễn và thi hành** quyền đó trong bytecode.

## 2. Phân biệt nest host, nest member và nestmate

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Nest host** | Class/interface giữ vai trò gốc, nhận diện nest và liệt kê những member được phép tham gia | `Invoice` là host |
| **Nest member** | Class/interface thuộc cùng nest, có thể truy cập `private` của các nestmates theo quy tắc JVM | `Invoice.Line`, `Invoice.Checker` |
| **Nestmate** | Hai class/interface **có cùng nest host** | `Invoice.Line` và `Invoice.Checker` là nestmates |
| **Singleton nest** | Nest chỉ có chính class/interface làm host và member duy nhất | Một top-level `PackageHelper` không có nested type |

Ví dụ tổ chức:

```text
Invoice                 <-- nest host
├── Line                <-- nest member
│   └── Detail          <-- nest member (lồng sâu hơn)
├── Checker             <-- nest member, cùng nest với Line/Detail
└── Audit               <-- nest member

PackageHelper           <-- top-level riêng, NẰM NGOÀI nest Invoice
```

Sơ đồ chỉ minh họa quan hệ type trong mã nguồn, không phải cây kế thừa. Những type `Line`, `Detail`, `Checker` cùng thuộc nest của `Invoice`, mặc dù `Detail` có class bao quanh trực tiếp là `Line`.

**Một class/interface thuộc đúng một nest.** Nếu không được ghi nhận là thành viên của nest khác, nó làm host của nest một phần tử của chính nó. Nest host cũng **là thành viên** của nest đó; đừng hiểu `NestMembers` chỉ liệt kê member ngoài host.

**Lưu ý về cách nói “cùng thực thể mã”:** Java compiler thường dùng nest cho những lớp nằm trong cùng cấu trúc top-level ở source, bao gồm static nested class, non-static inner class, interface lồng và những lớp local/anonymous được tạo từ cấu trúc đó. Nhưng **JVM xác định nest bằng class-file metadata hợp lệ**, không chỉ dựa vào tên có ký tự `$`, file `.java`, cách format code hay việc cùng package.

## 3. Ba API phản chiếu của `java.lang.Class` từ Java 11

Các phương thức kiểm tra nest được bổ sung trực tiếp vào `Class<?>`, vẫn được dùng trên JDK hiện đại:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `clazz.getNestHost()` | `Class<?>` | Trả về host của nest mà `clazz` thuộc về |
| `clazz.getNestMembers()` | `Class<?>[]` | Trả về những class/interface thuộc cùng nest, **bao gồm host** |
| `clazz.isNestmateOf(other)` | `boolean` | `true` nếu `clazz` và `other` có cùng nest host |

### `getNestHost()`

```java
Class<?> host = SomeNestedClass.class.getNestHost();
```

Đoạn minh họa cần thay `SomeNestedClass` bằng một class có thật. Với một nested class thông thường do `javac --release 11` tạo, kết quả là **class host top-level**. Với chính host, `host.getNestHost() == host`.

Theo hợp đồng `Class`, các kiểu nguyên thủy như `int.class`, `void.class` và các kiểu mảng như `String[].class` trả về **chính Class object của chúng** làm nest host. Đây là singleton nest; không phải “mảng kế thừa nest của kiểu phần tử”.

Nếu class-file nest metadata không hợp lệ hoặc không thể xác nhận host theo điều kiện nêu trong API, `getNestHost()` có thể coi class là host của chính nó. Không sử dụng một chuỗi ký tự tên class để “ép” kết quả thành host khác.

### `getNestMembers()`

```java
Class<?>[] members = Example.class.getNestMembers();
```

Mảng kết quả chứa **host ở vị trí đầu**; các member sau đó **không có thứ tự được bảo đảm**, và đặc tả còn cho phép giá trị lặp. Vì vậy, không kiểm thử bằng việc cố định thứ tự liệt kê mặc định; nên chuyển sang `Set` hoặc sắp xếp theo tên khi cần báo cáo dễ đọc. Với singleton nest, mảng chỉ gồm một phần tử.

API có thể cần tải/xác minh member được khai báo trong metadata. Nếu class file thiếu, không tương thích hoặc không thể xác nhận thành viên, `getNestMembers()` có thể ném **`LinkageError`**; điều này khác với một nest hợp lệ không có nhiều member.

### `isNestmateOf(Class<?>)`

```java
boolean sameNest = Alpha.class.isNestmateOf(Beta.class);
```

Kết quả phụ thuộc **cùng nest host** ở runtime. Phương thức không kiểm tra “có cùng package không?” và không kiểm tra “có kế thừa nhau không?”. Một class luôn là nestmate của chính nó. Với code kiểm thử, đây là cách rõ nhất để xác minh hai type có thực sự nằm chung nest.

## 4. Ví dụ Java hoàn chỉnh: outer, hai lớp lồng ngang hàng, inner và lớp cùng file

Ví dụ dưới đây làm rõ **quyền `private` hai chiều** và kiểm tra quan hệ nest bằng API Java 11. Điểm đặc biệt: `PackageNeighbor` là **top-level class thứ hai nằm trong cùng file `.java`**, nhưng không thuộc nest của `NestAccessDemo`.

Tạo file **`NestAccessDemo.java`**:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class NestAccessDemo {
    private final String secret = "host-secret";
    private static int value = 40;

    private static class Alpha {
        private String secret = "alpha-secret";

        static String readHost(NestAccessDemo host) {
            return host.secret; // Đọc private field của host.
        }

        static String readBeta(Beta beta) {
            return beta.secret; // Đọc private field của sibling.
        }
    }

    private static class Beta {
        private String secret = "beta-secret";

        static int advanceValue() {
            return ++value; // Sửa private static field của host.
        }
    }

    private class Inner {
        String readAlpha(Alpha alpha) {
            return alpha.secret; // Inner đọc private của Alpha.
        }
    }

    public static void main(String[] args) {
        NestAccessDemo host = new NestAccessDemo();
        Alpha alpha = new Alpha();
        Beta beta = new Beta();

        System.out.println("alphaReadsHost=" + Alpha.readHost(host));
        System.out.println("alphaReadsBeta=" + Alpha.readBeta(beta));
        System.out.println("hostReadsAlpha=" + alpha.secret);
        System.out.println("innerReadsAlpha=" +
                host.new Inner().readAlpha(alpha));
        System.out.println("betaUpdatesHost=" + Beta.advanceValue());

        System.out.println("hostName=" +
                Alpha.class.getNestHost().getSimpleName());
        System.out.println("hostIsOwnHost=" +
                (NestAccessDemo.class.getNestHost() == NestAccessDemo.class));
        System.out.println("siblingNestmates=" +
                Alpha.class.isNestmateOf(Beta.class));
        System.out.println("innerNestmate=" +
                Inner.class.isNestmateOf(Alpha.class));
        System.out.println("samePackageNotNestmate=" +
                Alpha.class.isNestmateOf(PackageNeighbor.class));

        // Sắp xếp tên vì getNestMembers() không cam kết thứ tự members.
        String members = Arrays.stream(Alpha.class.getNestMembers())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
        System.out.println("nestMembers=" + members);
        System.out.println("primitiveOwnNest=" +
                (int.class.getNestHost() == int.class));
    }
}

// Top-level khác, chỉ cùng package mặc định và cùng tệp mã nguồn.
class PackageNeighbor { }
```

Lệnh biên dịch/chạy (yêu cầu **JDK 17+** hoặc JDK 11 trở lên; dùng `--release 11` để xác nhận tính tương thích API/bytecode với Java 11):

```bash
javac --release 11 NestAccessDemo.java
java NestAccessDemo
```

**Stdout chính xác:**

```text
alphaReadsHost=host-secret
alphaReadsBeta=beta-secret
hostReadsAlpha=alpha-secret
innerReadsAlpha=alpha-secret
betaUpdatesHost=41
hostName=NestAccessDemo
hostIsOwnHost=true
siblingNestmates=true
innerNestmate=true
samePackageNotNestmate=false
nestMembers=Alpha,Beta,Inner,NestAccessDemo
primitiveOwnNest=true
```

**Đã kiểm tra thực tế:** chương trình trên biên dịch được bằng `javac --release 11` và cho đúng 12 dòng stdout như trên trên OpenJDK 24. Bytecode host có major version **55** và attribute `NestMembers`; `NestAccessDemo$Alpha.class` có attribute `NestHost: class NestAccessDemo`.

### Tại sao từng dòng quan trọng?

1. **`alphaReadsHost=host-secret`**: static nested class `Alpha` đọc field `private` của `NestAccessDemo` qua object `host`. “Static nested” có nghĩa không có implicit instance của outer, **không** có nghĩa mất quyền nestmate.
2. **`alphaReadsBeta=beta-secret`**: `Alpha` và `Beta` là **sibling nested classes**. Cả hai có chung host, nên `Alpha` được phép đọc field `private` của `Beta`.
3. **`hostReadsAlpha=alpha-secret`**: class host được phép truy cập field `private` của nested class theo chiều ngược lại.
4. **`innerReadsAlpha=alpha-secret`**: non-static `Inner` cũng thuộc cùng nest. Cú pháp `host.new Inner()` tạo instance inner gắn với `host`.
5. **`betaUpdatesHost=41`**: member `Beta` có thể cập nhật field `private static` của host; thành viên nest không chỉ được đọc private field mà còn có thể gọi private method/constructor hoặc ghi field nếu luật `final` cho phép.
6. **`hostName=NestAccessDemo`**: `Alpha.class.getNestHost()` trả về host.
7. **`hostIsOwnHost=true`**: host là thành viên của chính nest do nó làm host.
8. **`siblingNestmates=true` và `innerNestmate=true`**: quan hệ cùng nest không đòi hỏi hai class có quan hệ cha-con theo `extends`.
9. **`samePackageNotNestmate=false`**: `PackageNeighbor` có cùng file nguồn và package nhưng là top-level độc lập, nên **không tự nằm trong nest**.
10. **`nestMembers=...`**: bao gồm host và cả `Alpha`/`Beta`/`Inner`; code sắp xếp tên để kết quả ổn định. Nếu không sắp xếp, thứ tự sau host do API không quy định.
11. **`primitiveOwnNest=true`**: `int.class` là host của singleton nest chứa chính primitive class object đó.

**Giới hạn:** chương trình không thử truy cập `PackageNeighbor` vào `Alpha.secret`, vì đoạn mã đó sẽ không được trình biên dịch chấp nhận nếu chỉ dùng cú pháp truy cập private thông thường. Không cần thử truy cập bất hợp lệ để chứng minh quan hệ không cùng nest; `isNestmateOf(...)` đã thể hiện chính xác điều kiện.

## 5. Nest host và member được ghi trong bytecode ra sao?

Trước Java 11, các type lồng nhau ở source Java đã có thể dùng `private` của nhau, nhưng ở JVM cấp class file, mỗi nested type là một class riêng. Trình biên dịch thường phải tạo **synthetic accessors** (phương thức truy cập trung gian có visibility rộng hơn private) để bytecode giao tiếp được. Java 11 giải quyết điểm lệch này bằng **nest-based access control** ở JVM: các class cùng nest có thể kiểm tra quyền và truy cập private trực tiếp.

Hai class-file attributes mới theo **JEP 181**:

| Attribute | Thường nằm ở đâu | Nội dung |
| --- | --- | --- |
| `NestMembers` | `.class` của **nest host** | Danh sách các member được host công nhận, **không tính host trong danh sách attribute** |
| `NestHost` | `.class` của **nest member** không phải host | Trỏ tới tên class/interface làm nest host |

Ở runtime, **host tự nằm trong nest**, nên `getNestMembers()` đưa host vào kết quả dù `NestMembers` attribute thường chỉ liệt kê các member ngoài host.

Java 11 class file có major version **55.0**. Những attributes trên được định nghĩa cho class file từ version 55; class files cũ hơn không dùng chúng. Với mã trên, chạy:

```bash
javap -v NestAccessDemo
javap -v 'NestAccessDemo$Alpha'
```

Trong terminal kiểu Unix/Linux/macOS, đặt tên có `$` trong dấu nháy đơn để shell không tự khai triển biến. Trong PowerShell, cũng có thể dùng dấu nháy đơn. Phần output của `javap -v` rất dài, hãy tìm hai đoạn liên quan:

```text
major version: 55
NestMembers:
```

Ở class file của `NestAccessDemo$Alpha`, tìm:

```text
NestHost: class NestAccessDemo
```

Đây là **những dòng trích có ý nghĩa**, không phải toàn bộ stdout của `javap`. Thứ tự và thông tin constant-pool xung quanh có thể thay đổi theo JDK.

**Cơ chế hai phía:** member **khai báo host** bằng `NestHost`, còn host **cho phép member** bằng `NestMembers`. JVM kiểm tra sự tương thích của mối quan hệ này, kể cả điều kiện cùng **runtime package**. Không thể lấy một class bất kỳ ở package khác rồi chỉ tự thêm `NestHost` để nhận quyền truy cập private từ host.

Các metadata `InnerClasses` và `EnclosingMethod` có thể mô tả quan hệ khai báo/enclosing của Java source, nhưng **không phải chính chúng** cấp quyền nestmate ở JVM Java 11+. Tránh suy ra nest bằng cách tách tên class theo dấu `$`: ký tự đó cũng có thể xuất hiện trong tên do ứng dụng tự tạo, và không phải định dạng chứng thực quyền truy cập.

## 6. Các nhóm class thường thuộc cùng nest

### 6.1. Static nested class

`static class Helper` đặt trong một top-level class thường thuộc nest của top-level đó. Nó **không có** implicit outer instance; muốn đọc field instance của outer, phải có object reference. Ví dụ `Alpha.readHost(host)` ở trên.

### 6.2. Non-static inner class

`class Inner` không có `static`, thường gắn với một instance bao quanh và vẫn thuộc **cùng nest** như host và các sibling types. Quy tắc về outer instance là quy tắc khởi tạo/object model, **khác** với quyền truy cập private cấp JVM.

### 6.3. Lớp lồng nhiều tầng và nested interface

Một kiểu được khai báo trong nested class khác thường vẫn cùng **nest host top-level**, không tạo nest host mới ở mỗi tầng. Ví dụ `Outer.Middle.Deep` có thể có cùng host `Outer`. Một interface được khai báo lồng cũng có thể tham gia nest theo quy tắc class-file của Java 11.

### 6.4. Local class và anonymous class

Trong mã nguồn, local class khai báo bên trong method và anonymous class tạo bằng cú pháp `new SomeType() { ... }` thường được `javac` ghi nhận là các nest members của top-level host liên quan. Tuy nhiên, tên class như `Outer$1` hoặc `Outer$1Local` do compiler sinh **không phải API ổn định** để viết logic nghiệp vụ. Nếu cần kiểm tra chính xác một class ở runtime, dùng `getNestHost()`/`isNestmateOf(...)` thay vì đoán từ tên.

`getNestMembers()` không đồng nghĩa với `getDeclaredClasses()`:

- `getDeclaredClasses()` thông thường phản ánh những **member class/interface được khai báo trực tiếp** bên trong class đang xét; không dùng để liệt kê mọi local/anonymous class trong method.
- `getNestMembers()` dựa vào metadata của **toàn nest**, có thể bao gồm nested types nhiều tầng, local/anonymous types, cùng host. Nó trả cả host và không hứa thứ tự member.

### 6.5. Các class không tự thành nestmate

- Hai top-level class trong **một file** như `NestAccessDemo` và `PackageNeighbor`.
- Hai class chỉ **cùng package**, không có nest relationship.
- Một class con `extends Parent` nếu nó không nằm trong cùng nest của `Parent`.
- Một class sinh động ở runtime (dynamic proxy hoặc bytecode tool) chỉ vì có tên “giống nested class”. Muốn quyền nestmate phải đáp ứng cơ chế class-definition và validation phù hợp, không chỉ đổi tên.

## 7. Quyền truy cập `private` và ranh giới bảo mật

### Không phải “mọi class cùng package được đọc private”

Tại runtime, `private` member có thể được truy cập từ **chính declaring class** hoặc từ **nestmates hợp lệ** theo quy tắc JVM. Một package có thể chứa nhiều nest độc lập; `package-private` và `private` vẫn là hai mức kiểm soát khác nhau.

Tương tự, **kế thừa** không làm `private` của superclass tự trở thành truy cập trực tiếp được từ subclass. Nếu một subclass cũng là nested class cùng nest của superclass thì quy tắc nest có thể áp dụng, nhưng **không phải vì `extends`**.

### Không phải “bỏ qua module system”

Java Platform Module System (**JPMS**) vẫn có các quy tắc về việc nhìn thấy class/module, `exports`/`opens` và quyền truy cập thông qua reflection. Nest-based access chỉ điều chỉnh việc JVM xem các class cùng nest khi kiểm tra `private`; nó **không phải một giấy phép mở mọi package của mọi module**.

Các API reflection/`MethodHandles.Lookup` cũng chịu ảnh hưởng của nestmate access theo quy tắc tương ứng, nhưng một thư viện ở class/module **bên ngoài nest** không tự có quyền đọc private chỉ bằng cách gọi `getDeclaredField(...)`. Các thao tác reflective sâu phải tuân theo ràng buộc access/module của JDK hiện hành; đừng coi `setAccessible(true)` như cách chung có thể vượt mọi ranh giới module.

### Không chỉ nhìn vào tên hoặc file khi kiểm tra quyền

JVM cần mối quan hệ **nest host/member hợp lệ**, có tham chiếu hai phía và cùng **runtime package** (trong đó runtime class identity/class-loader cũng có ý nghĩa). Đổi tên file `.class`, tên chứa `$` hoặc đặt file vào cùng thư mục không thay được việc xác minh class-file metadata hợp lệ.

Một ứng dụng không nên tự chỉnh bytecode `NestMembers`/`NestHost` để truy cập dữ liệu riêng của thư viện khác. Đây là cơ chế **của ngôn ngữ/trình biên dịch và hệ thống lớp đáng tin**, không phải một API chia sẻ bí mật xuyên trust boundary.

## 8. Phân biệt với các cách truy vấn cấu trúc class khác

| API/khái niệm | Câu hỏi trả lời | Có cùng nghĩa nestmate không? |
| --- | --- | --- |
| `Class.getNestHost()` | Ai là host của nest này? | Có, trực tiếp |
| `Class.getNestMembers()` | Các member của toàn nest là ai? | Có, trực tiếp |
| `Class.isNestmateOf(other)` | Hai class có chung host không? | Có, trực tiếp |
| `Class.getDeclaringClass()` | Class nào khai báo **member class** này? | Không; khai báo trực tiếp có thể khác host ở mức top-level |
| `Class.getEnclosingClass()` | Class lexical enclosing của local/anonymous/nested class là gì? | Không; phản ánh quan hệ enclosing, không tự xác minh nest |
| `Class.getDeclaredClasses()` | Những member types nào được khai báo trực tiếp trong class này? | Không; khác danh sách toàn nest |
| `Class.getSuperclass()` | Class cha theo `extends` là gì? | Không; kế thừa không đồng nghĩa nestmate |
| `Class.getPackageName()` | Tên package của class là gì? | Không; package chung chưa đủ |

Ví dụ `Outer.Middle.Deep`: `Deep.class.getDeclaringClass()` có thể là `Middle.class`, trong khi `Deep.class.getNestHost()` là `Outer.class`. Do đó không dùng `getDeclaringClass()` để suy ra “host phải là declaring class trực tiếp”.

## 9. Tương thích khi biên dịch và triển khai

### 9.1. Source cũ vẫn hoạt động

JEP 181 không buộc bạn phải sửa lại mọi class lồng nhau; Java source đã cho phép outer/inner truy cập private của nhau. Mã biên dịch trước Java 11 có thể dùng **synthetic accessor methods** để đạt hành vi tương tự, và Java 11+ vẫn có thể chạy bytecode cũ phù hợp. Không có lý do để tự viết những accessor `package-private` chỉ để thay thế cơ chế nest của JDK hiện tại.

Khi cần chạy trên **Java 11**, biên dịch bằng `javac --release 11` (cùng API/bytecode target), hoặc dùng JDK 11 để biên dịch. `--release 11` tạo class file version 55, giúp compiler ghi các thuộc tính nest cần thiết. Không đánh đồng “chạy javac trên JDK 17/21/24” với “tự động cho bytecode tương thích JDK 11” nếu chưa đặt `--release` phù hợp.

### 9.2. Không triển khai lẫn lộn các file `.class`

Một source top-level có thể tạo nhiều file `.class`, chẳng hạn:

```text
NestAccessDemo.class
NestAccessDemo$Alpha.class
NestAccessDemo$Beta.class
NestAccessDemo$Inner.class
PackageNeighbor.class
```

Nếu cập nhật **chỉ** class host nhưng để các nested class cũ (hoặc ngược lại), metadata của hai phía có thể lệch nhau. Tùy trường hợp, lúc tải/xác minh hoặc truy cập private có thể gặp `LinkageError`, trong đó có `IncompatibleClassChangeError` hoặc `IllegalAccessError`. Khi deploy, **đóng gói và triển khai cùng phiên bản** các class liên quan như một đơn vị, nhất là khi có bytecode weaving, shading hoặc class-loader riêng.

Java 11 Javadoc có chi tiết: `getNestHost()` có thể trả chính class khi không thể công nhận host hợp lệ; `getNestMembers()` có thể ném `LinkageError` khi tải/validate member bị lỗi. Đừng biến những trường hợp lỗi classpath/classloader thành “nest đang trống hợp lệ” mà không chẩn đoán.

### 9.3. Kiểm tra bytecode thay vì dựa vào suy đoán

Nếu cần biết compiler thực sự xuất ra attributes nào:

```bash
javap -v NestAccessDemo
javap -v 'NestAccessDemo$Alpha'
```

Chú ý `major version: 55`, `NestMembers` ở host và `NestHost` ở nested class. Việc có những attributes này và quan hệ hợp lệ ở runtime là cơ sở để JVM nhận biết nest; **không phải** chỉ vì IDE thể hiện các type cùng nằm trong một cây.

## 10. Các lỗi phổ biến

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Nghĩ hai class trong cùng `.java` luôn cùng nest | File nguồn không định nghĩa ranh giới nest | Kiểm tra `getNestHost()` hoặc `isNestmateOf(...)` |
| Nghĩ cùng package được truy cập `private` | `private` và package-private khác nhau | Chỉ class/nestmates hợp lệ hoặc cơ chế reflection được cấp quyền theo chuẩn |
| Nghĩ `NestedA`/`NestedB` không thể đọc private của nhau | Chúng có thể là sibling nestmates cùng host | Dùng đúng tham chiếu object/static và biên dịch Java 11+ |
| Nghĩ chỉ non-static inner class là nestmate | Static nested class cũng thuộc nest khi metadata hợp lệ | Phân biệt quyền truy cập với nhu cầu outer instance |
| Lấy `getDeclaredClasses()` làm danh sách toàn nest | API đó không liệt kê mọi member của toàn nest | Dùng `getNestMembers()` |
| Cố định thứ tự phần tử sau host của `getNestMembers()` | Thứ tự còn lại không được bảo đảm | Sort/so sánh tập nếu mục tiêu là kiểm thử |
| Dựa vào ký tự `$` trong tên class để nhận dạng host | Tên không xác thực nest relationship | Dùng API `Class` hoặc classfile attributes |
| Dùng `getDeclaringClass()` thay `getNestHost()` | Lớp declaring trực tiếp có thể không phải host top-level | Hỏi đúng API theo mục đích |
| Kết luận `extends` tạo quyền `private` | Kế thừa không tự cấp quyền private | Kiểm tra nest và quyền truy cập tương ứng |
| Triển khai host/member từ hai phiên bản build khác nhau | Metadata có thể thiếu hoặc không tương thích | Deploy nguyên bộ classfiles từ cùng build |
| Cho rằng nestmate bỏ qua JPMS/`opens` | Module/reflection còn kiểm soát truy cập | Giữ ranh giới module và API reflection hợp lệ |
| Gặp `LinkageError` rồi tự gắn thêm `NestHost` thủ công | Có thể vi phạm xác minh hai chiều/runtime package | Sửa build/package/classloader và metadata qua compiler/tool đáng tin |

## 11. Câu hỏi tự kiểm tra

**Câu 1:** `Outer` có `static class A` và `class B`. `A` và `B` có thể là nestmates không dù một lớp static và một lớp non-static?

**Đáp án:** Có. Cả hai thường được compiler Java 11+ đưa vào cùng nest có host `Outer`. Static/non-static ảnh hưởng đến outer instance, không quyết định riêng quyền nestmate.

**Câu 2:** Hai top-level classes `A` và `B` được khai báo trong cùng file `Test.java`, cùng package. Chắc chắn `A.class.isNestmateOf(B.class)` là `true` không?

**Đáp án:** Không. Chúng không tự cùng nest chỉ vì nằm chung file/package. Nếu không có metadata nest hợp lệ cùng host, mỗi top-level type thuộc nest riêng.

**Câu 3:** `getNestMembers()` có bao gồm host không? Có thể tin thứ tự các member không?

**Đáp án:** Có **host ở phần tử đầu**; các member còn lại không có thứ tự bảo đảm. Đặc tả cho phép lặp, nên khi xử lý logic không được dựa vào thứ tự hay giả định tên không trùng.

**Câu 4:** `Outer.Middle.Deep.class.getDeclaringClass()` và `getNestHost()` có bắt buộc trả về cùng class không?

**Đáp án:** Không. Declaring class trực tiếp có thể là `Middle`, nhưng nest host có thể là `Outer`.

**Câu 5:** Nest-based access từ Java 11 làm source Java có thêm quyền truy cập `private` hoàn toàn mới không?

**Đáp án:** Không. Nó đưa mô hình quyền truy cập đã được ngôn ngữ cho phép cho nested types xuống JVM trực tiếp, nhờ hai classfile attributes `NestHost` và `NestMembers`.

**Câu 6:** Vì sao JVM không chấp nhận một member bất kỳ tự khai `NestHost=SensitiveHost` rồi đọc private của host?

**Đáp án:** Vì host phải xác nhận membership qua `NestMembers` và cùng runtime package hợp lệ; không chỉ dựa trên lời tự nhận/tên class của member.

**Câu 7:** `int.class.getNestHost()` trả về gì?

**Đáp án:** Trả chính `int.class`. Primitive, `void` và array classes có singleton nest.

**Câu 8:** Một thư viện reflection bên ngoài nest có được mặc nhiên gọi private method chỉ vì có `getDeclaredMethod(...)` không?

**Đáp án:** Không. Tra cứu member và quyền sử dụng member là hai việc khác nhau; Java access checks và module access vẫn áp dụng, cần cơ chế truy cập được cấp quyền phù hợp.

**Ghi nhớ:** **Nest host** là class/interface đại diện cho một **nhóm lớp cùng thực thể mã**, và **nest member** là class/interface có cùng host. Java 11+ dùng `NestHost`/`NestMembers` ở classfile để JVM cho phép những **nestmates hợp lệ** truy cập `private` của nhau mà không phải dựa vào synthetic accessors. Dùng **`getNestHost()`, `getNestMembers()`, `isNestmateOf()`** để kiểm tra; không nhầm nest với một file `.java`, package, superclass hoặc quan hệ enclosing trực tiếp.

**Tài liệu chính thức:** [OpenJDK JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181); [Oracle Java SE 11 — java.lang.Class](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Class.html); [Java SE 11 Release Notes — JEP 181](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html); [Java SE 25 — java.lang.Class](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html); [Java Virtual Machine Specification — `4.7.28 và `4.7.29](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html).
