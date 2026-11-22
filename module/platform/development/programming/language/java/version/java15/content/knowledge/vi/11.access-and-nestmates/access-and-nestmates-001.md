# Nest host, nest member và truy cập thành viên private trong Java

> **Bối cảnh:** Chủ đề “Truy cập và nest”, module Java 15. Bài học dùng cơ chế **nest-based access control** chính thức của JVM (có từ Java 11 và tiếp tục được hỗ trợ) cùng khả năng tạo **hidden nestmate** bằng `MethodHandles.Lookup.defineHiddenClass(..., NESTMATE)` (từ Java 15). Tất cả ví dụ dùng API đã chuẩn hóa, chạy được trên JDK 17 trở lên, không dùng preview feature hoặc các thủ thuật truy cập lỗi thời.

## 1. Vì sao JVM cần khái niệm nest?

Trong mã Java, các lớp được khai báo lồng nhau thường được tổ chức như một đơn vị logic. Lớp bên trong có thể dùng thành viên `private` của lớp bao ngoài; lớp bao ngoài cũng có thể truy cập thành viên `private` của lớp lồng bên trong khi quy tắc của ngôn ngữ cho phép.

```java
public class Library {
    private static String secret() {
        return "key";
    }

    static class Reader {
        static String read() {
            return secret(); // Hợp lệ: Reader nằm trong Library.
        }

        private static int code() {
            return 7;
        }
    }

    public static void main(String[] args) {
        System.out.println(Reader.read()); // key
        System.out.println(Reader.code()); // 7
    }
}
```

Đặt tên tệp là `Library.java`; chạy `javac Library.java` và `java Library`. Stdout:

```text
key
7
```

Tuy nhiên, Java compiler có thể tạo **nhiều class file riêng** từ một cấu trúc nguồn:

```text
Library.java
    |
    +-- Library.class
    +-- Library$Reader.class
```

Với Java hiện đại, JVM hiểu rằng những class file ấy có thể thuộc **cùng một nest**. Nest-based access control cho phép các **nestmate** truy cập thành viên `private` của nhau theo quy tắc của JVM, thay vì coi mọi class file là một ranh giới `private` tuyệt đối.

**Định nghĩa:**

- **Nest:** tập hợp các class/interface cùng runtime package có quan hệ thành viên nest được JVM công nhận; một thành viên đóng vai trò **nest host**.
- **Nest host:** class hoặc interface đại diện cho nest; với mã `javac` thông thường, class top-level bao ngoài thường là host.
- **Nest member:** class/interface thuộc nest đó, bao gồm **chính host**.
- **Nestmate:** hai class/interface có cùng nest host. Một class cũng là nestmate của chính nó.

Khái niệm này là **quan hệ trong JVM**, không chỉ là cách thụt lề hay cách đặt dấu `$` trong tên class.

## 2. Ba API phản chiếu cần nắm

Các phương thức nằm trong `java.lang.Class` và vẫn được hỗ trợ ở những JDK hiện hành:

```java
public Class<?> getNestHost()
public Class<?>[] getNestMembers()
public boolean isNestmateOf(Class<?> c)
```

Cả ba được bổ sung từ **Java 11**. Không cần dùng JDK 11 để thực hành: chúng có sẵn trong Java 17, 21, 25 và các bản Java mới hơn.

### 2.1. `getNestHost()`: hỏi “ai là host?”

```java
Class<?> host = SomeClass.class.getNestHost();
```

- Nếu class đang xét thuộc một nest có host khác chính nó, kết quả là đối tượng `Class<?>` của host.
- Nếu nest chỉ có một thành viên, host **là chính class ấy**; phép so sánh `type.getNestHost() == type` là `true`.
- Với array class, kiểu primitive hoặc `void.class`, `getNestHost()` trả về chính `Class` ấy theo đặc tả.
- Với class thường do `javac` sinh từ cấu trúc lồng nhau, host thường là class top-level của tổ chức nguồn.

Ví dụ:

```java
Class<?> host = Library.Reader.class.getNestHost();
boolean same = host == Library.class; // true
```

Đoạn này được đặt ở mã khác **sau khi** class `Library` của ví dụ trước đã được biên dịch. Phép kiểm tra này trả `true` với class file do trình biên dịch Java hiện đại tạo từ ví dụ.

**Đừng nhầm “host” với superclass**. Nest không phải hệ thống kế thừa; `getSuperclass()` và `getNestHost()` giải đáp hai câu hỏi khác nhau.

### 2.2. `isNestmateOf(...)`: kiểm tra quan hệ nest trực tiếp

```java
boolean sameNest =
        Library.Reader.class.isNestmateOf(Library.class);
```

Kết quả là `true` vì hai class có cùng host. Đây là lựa chọn đơn giản khi muốn trả lời câu hỏi “hai class này có phải nestmate không?”.

Theo định nghĩa:

```text
A là nestmate của B
     <=>
A.getNestHost() và B.getNestHost()
trỏ tới cùng Class<?> đại diện cho host
```

Với hai class hoàn toàn độc lập được khai báo trong **cùng một package**, quan hệ nest **không tự xuất hiện**. Chỉ ở cùng package hoặc cùng class loader không đủ.

Trong công cụ phân tích class file, hãy dùng `isNestmateOf` hoặc `getNestHost` thay vì suy đoán từ chuỗi tên.

### 2.3. `getNestMembers()`: liệt kê thành viên được ghi nhận

```java
Class<?>[] members = Library.class.getNestMembers();
```

Những điểm cần đọc kỹ:

1. Mảng được trả về có phần tử **đầu tiên là nest host**.
2. Các phần tử tiếp theo là những class/interface được host ghi trong thuộc tính `NestMembers` của class file và được JVM xác nhận thuộc nest.
3. **Thứ tự của các phần tử tiếp theo không được bảo đảm**, và tài liệu cho phép có phần tử trùng lặp. Đừng kiểm thử bằng cả chuỗi `Arrays.toString(...)` hoặc vị trí phần tử thứ hai trở đi.
4. Nếu là nest chỉ gồm chính class ấy, mảng thường chỉ chứa một phần tử là host. Với primitive, array và `void.class`, API trả mảng chỉ chứa đối tượng `Class` được hỏi.
5. **Điểm đặc biệt của Java 15+:** danh sách này **không bao gồm hidden class được thêm động vào nest bằng `defineHiddenClass(..., NESTMATE)`**, bởi những lớp ấy không được ghi trong thuộc tính `NestMembers` tĩnh của host.

Vì thế, với một hidden class `H` mới thêm động, cả hai mệnh đề sau có thể đồng thời đúng:

```java
boolean yes = H.isNestmateOf(Host.class); // true
boolean listed = java.util.Arrays.asList(
        Host.class.getNestMembers()).contains(H); // false
```

Đây là snippet với `H` và `Host` mang nghĩa minh họa, **không phải chương trình độc lập**. Mối quan hệ nest vẫn có thật dù `getNestMembers()` không liệt kê đầy đủ mọi **hidden nestmate động**.

## 3. Nest được thể hiện trong class file như thế nào?

Cơ chế nest-based access control là quy tắc chính thức của JVM. Class file có hai loại thuộc tính liên quan:

| Thuộc tính class file | Thường xuất hiện ở đâu? | Vai trò |
| --- | --- | --- |
| `NestHost` | Class/interface thành viên không phải host | Ghi class/interface mà thành viên **tuyên bố** là nest host |
| `NestMembers` | Class/interface làm host | Liệt kê các thành viên **được host công nhận** là cùng nest |

Đối với cấu trúc `Library` ở ví dụ đầu:

```text
Library.class
    NestMembers: Library$Reader

Library$Reader.class
    NestHost: Library
```

Sơ đồ trên mô tả **quan hệ thông thường** mà trình biên dịch tạo. Nó không có nghĩa class file phải chứa đúng chuỗi văn bản ở dạng này.

### Tại sao không thể tự ghi tên host là xong?

JVM kiểm tra tính hợp lệ của quan hệ nest, bao gồm **runtime package** và sự nhất quán giữa thông tin host/member. Một class giả mạo `NestHost` để xin vào nest của một host bất kỳ sẽ không tự được trao quyền truy cập `private`.

- Host và member thông thường phải đáp ứng điều kiện package, class loader/module phù hợp của runtime.
- Host phải công nhận thành viên được nêu theo cơ chế class file, không chỉ vì tên thành viên có tiền tố giống host.
- Class file không nhất quán có thể làm quá trình xác định host hoặc truy cập thành viên thất bại với **linkage/access error** tương ứng.
- Một class/interface không khai báo `NestHost` được coi là host của nest của chính nó, trừ những quy tắc riêng dành cho hidden nestmate động.

Một class `com.example.Outer$Fake` không thể tự trở thành nestmate chỉ nhờ dấu `$` trong tên.

### Quan hệ source code và quan hệ JVM

Cú pháp Java nói gì **được phép viết trong mã nguồn**; thuộc tính nest nói JVM làm gì **khi liên kết và kiểm tra quyền truy cập bytecode**.

Do đó:

- Các class lồng nhau theo cú pháp Java có thể trực tiếp viết code tham chiếu thành viên `private` của nhau theo quy tắc ngôn ngữ.
- Hai class top-level độc lập không được phép tự viết truy cập `private` của nhau chỉ vì cùng package.
- Runtime có thể sinh một **hidden nestmate** hợp lệ để truy cập `private` của nest theo cơ chế JVM, mặc dù hidden class ấy không có khai báo top-level/nested tương ứng trong file nguồn.

Đừng đánh đồng nest với `public`, `protected`, package-private hay kế thừa. Nest mở rộng cách JVM kiểm tra `private` **giữa các thành viên cùng nest**, không phá bỏ các quy tắc module hoặc mọi hạn chế bảo mật khác.

## 4. Truy cập `private` giữa các nestmate

Trong Java hiện đại, điều kiện cốt lõi về truy cập private ở mức JVM là: một class/interface có thể truy cập thành viên private được khai báo trong **chính nó hoặc một class/interface cùng nest**, với bytecode và các điều kiện liên kết hợp lệ.

Ví dụ trong class `Library`:

```java
private static String secret() { return "key"; }

static class Reader {
    static String read() {
        return secret(); // Thành viên nest gọi private của host.
    }

    private static int code() { return 7; }
}

// Trong phương thức của Library:
int number = Reader.code(); // Host gọi private của member.
```

Đây là **các snippet rút từ chương trình ở phần 1**; không nên ghép ngoài class rồi mong chúng tự biên dịch.

Bộ đôi truy cập đi **hai chiều**:

- `Reader` đọc phương thức private của host.
- Host gọi phương thức private của `Reader`.

Đó là lý do `private` không có nghĩa “chỉ có các dòng trong đúng một file `.class` mới truy cập được”. Trong Java hiện đại, nestmate được JVM công nhận còn có thể truy cập theo cơ chế phù hợp.

### Vì sao không nên dựa vào tên nested class?

`Outer$Inner` thường là binary name mà `javac` dùng cho nested class. Nhưng tên này **không phải bằng chứng đủ** về nest:

- JVM không phân loại nest bằng cách tìm dấu `$`.
- Một class có tên chứa `$` không tự được host công nhận.
- Local/anonymous class có thể dùng cấu trúc tên đặc biệt nhưng vẫn phải kiểm tra nest theo metadata/runtime.
- Hidden class có tên runtime đặc biệt với hậu tố do JVM tạo ra; lại càng không thể suy luận nest từ tên.

Dùng `Class.getNestHost()` và `Class.isNestmateOf(...)` để hỏi đúng cơ chế.

## 5. Hidden class có thể tham gia nest bằng `NESTMATE`

**Hidden class** là một class/interface được tạo từ bytecode lúc chạy bằng `MethodHandles.Lookup.defineHiddenClass(...)`. Đây là tính năng chính thức từ Java 15.

API chính:

```java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException
```

Tùy chọn `MethodHandles.Lookup.ClassOption.NESTMATE` có ý nghĩa:

> Tạo hidden class mới như **một nestmate của lookup class**, tức nó thuộc nest có cùng host với lookup class và có khả năng truy cập thành viên private của các class/interface khác cùng nest theo quy tắc JVM.

So sánh:

| Cách tạo hidden class | Nest host của hidden class | Quan hệ với lookup class |
| --- | --- | --- |
| `lookup.defineHiddenClass(bytes, true)` | **Chính hidden class mới**: một nest riêng theo mặc định | Không tự là nestmate của lookup class |
| `lookup.defineHiddenClass(bytes, true, NESTMATE)` | **Nest host của lookup class** | Hidden class mới là nestmate của lookup class |

Ví dụ nếu đang chạy trong class host `App`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE);

Class<?> hidden = hiddenLookup.lookupClass();
boolean result = hidden.isNestmateOf(App.class); // true
```

Đây là snippet cần có bytecode hợp lệ `classBytes` và class `App` thực sự chứa đoạn code. `defineHiddenClass` trả về **Lookup của hidden class**, không trực tiếp trả về `Class<?>`. Gọi `lookupClass()` để nhận class ấy.

### Nest host nào được chọn?

Với `NESTMATE`, host được xác định từ **lookup class của Lookup thực hiện lời gọi**, không phải từ một `NestHost` có thể tồn tại trong bytecode nguồn. Nếu lookup class đã nằm trong một nest có host `H`, hidden class được thêm làm nestmate cùng host `H`.

Vì thế, hidden class tạo từ bytecode trước đó của một nested class vẫn có thể nhận quan hệ nest **mới** theo `NESTMATE`. Ví dụ hoàn chỉnh phía dưới sử dụng đúng đặc điểm này.

### Vì sao `getNestMembers()` không thấy hidden nestmate?

Thông tin `NestMembers` trong class file của host là **danh sách tĩnh**. Hidden class chỉ được tạo khi chương trình đang chạy; host không cần và không thể cập nhật class file để chèn tên mới.

Do đó:

- `hidden.getNestHost() == host` có thể là `true`.
- `hidden.isNestmateOf(host)` có thể là `true`.
- `Arrays.asList(host.getNestMembers()).contains(hidden)` vẫn là `false`.

Không có mâu thuẫn: `getNestMembers()` không phải API liệt kê mọi hidden class từng được tạo, cũng không là **registry động** của tất cả nestmate.

## 6. Ví dụ chạy thật: host, member, hidden class và truy cập private

Mục đích của ví dụ:

1. Kiểm tra host và member do `javac` tạo.
2. Chứng minh host và member truy cập private **hai chiều**.
3. Chứng minh một top-level class khác **cùng package** nhưng **không** cùng nest.
4. Định nghĩa hidden class **không có `NESTMATE`**, kiểm tra nest host là chính nó.
5. Định nghĩa hidden class **có `NESTMATE`**, cho nó gọi phương thức private của host.
6. Chứng minh `getNestMembers()` của host không liệt kê hidden nestmate động.

### 6.1. Toàn bộ tệp `NestAccessDemo.java`

Đặt toàn bộ mã sau vào một file `NestAccessDemo.java`, không tách riêng nested class `Template`:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;

public class NestAccessDemo {
    private static String hostSecret() {
        return "KEY-42";
    }

    static class Member {
        static String readHostSecret() {
            return hostSecret();
        }

        private static int memberSecret() {
            return 7;
        }
    }

    // javac tạo file NestAccessDemo$Template.class.
    // Mã nguồn Template thuộc cùng nest với host.
    static class Template {
        static String readHostSecret() {
            return hostSecret();
        }
    }

    public static void main(String[] args) throws Throwable {
        Class<?> host = NestAccessDemo.class;
        Class<?> member = Member.class;

        System.out.println("host.self="
                + (host.getNestHost() == host));
        System.out.println("member.host="
                + (member.getNestHost() == host));
        System.out.println("member.mate="
                + member.isNestmateOf(host));
        System.out.println("member.readHost="
                + Member.readHostSecret());
        System.out.println("host.readMemberPrivate="
                + Member.memberSecret());

        Class<?>[] recorded = host.getNestMembers();
        System.out.println("members.firstHost="
                + (recorded[0] == host));
        System.out.println("members.containsMember="
                + Arrays.asList(recorded).contains(member));
        System.out.println("unrelated.mate="
                + UnrelatedNest.class.isNestmateOf(host));

        // Đọc bytecode của nested class đã được javac tạo.
        byte[] bytes;
        try (InputStream in = host.getResourceAsStream(
                "NestAccessDemo$Template.class")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing NestAccessDemo$Template.class");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Không chọn NESTMATE: hidden class có nest riêng.
        MethodHandles.Lookup plainLookup =
                lookup.defineHiddenClass(bytes, true);
        Class<?> plain = plainLookup.lookupClass();
        System.out.println("plain.hidden=" + plain.isHidden());
        System.out.println("plain.selfHost="
                + (plain.getNestHost() == plain));
        System.out.println("plain.mateHost="
                + plain.isNestmateOf(host));

        // Có NESTMATE: cùng nest host với lookup class.
        MethodHandles.Lookup nestLookup =
                lookup.defineHiddenClass(
                        bytes,
                        true,
                        MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> hidden = nestLookup.lookupClass();

        System.out.println("hidden.hidden="
                + hidden.isHidden());
        System.out.println("hidden.host="
                + (hidden.getNestHost() == host));
        System.out.println("hidden.mateHost="
                + hidden.isNestmateOf(host));
        System.out.println("members.containsHidden="
                + Arrays.asList(host.getNestMembers())
                        .contains(hidden));

        // Lookup của hidden class có quyền truy cập hợp lệ.
        MethodHandle action = nestLookup.findStatic(
                hidden,
                "readHostSecret",
                MethodType.methodType(String.class));
        String answer = (String) action.invokeExact();
        System.out.println("hidden.readHostPrivate=" + answer);

        System.out.println("primitive.selfHost="
                + (int.class.getNestHost() == int.class));
    }
}

// Cùng unnamed package, nhưng KHÔNG phải nested class.
class UnrelatedNest {
}
```

### 6.2. Cách biên dịch và chạy

Yêu cầu **JDK 17 trở lên**. Ví dụ dùng API chính thức của `java.base`, không cần thêm thư viện, `--add-opens`, `--enable-preview` hay module phụ.

```bash
javac -encoding UTF-8 NestAccessDemo.java
java NestAccessDemo
```

Cách chạy thông thường là mở terminal ở thư mục chứa file sau khi biên dịch, nơi `javac` tạo các tệp `.class` tương ứng.

**Stdout chính xác** khi dùng nguyên mã và class files mới biên dịch cùng nhau:

```text
host.self=true
member.host=true
member.mate=true
member.readHost=KEY-42
host.readMemberPrivate=7
members.firstHost=true
members.containsMember=true
unrelated.mate=false
plain.hidden=true
plain.selfHost=true
plain.mateHost=false
hidden.hidden=true
hidden.host=true
hidden.mateHost=true
members.containsHidden=false
hidden.readHostPrivate=KEY-42
primitive.selfHost=true
```

### 6.3. Giải thích từ đầu tới cuối

**Nhóm host và member.** `NestAccessDemo.class` là host của nest thông thường do `javac` tạo. `Member.class` là nest member, nên `getNestHost()` trả host và `isNestmateOf` là `true`. Phương thức `Member.readHostSecret()` gọi phương thức `private static` của host; host gọi phương thức `private static` của member. Đó là hai trường hợp private access thực sự, không phải chỉ đọc hằng `static final` đã bị compiler inline.

**Danh sách tĩnh.** Phần tử đầu tiên của `getNestMembers()` là host. `Member` xuất hiện vì được ghi vào metadata của host. Ví dụ **không** dựa vào thứ tự của các member sau host.

**Không cùng nest dù cùng package.** `UnrelatedNest` là top-level class khác trong cùng file, cùng unnamed package, nhưng không được khai báo lồng trong `NestAccessDemo`. Vì không tham gia nest, `UnrelatedNest.class.isNestmateOf(host)` là `false`. Cùng file `.java` không có nghĩa cùng nest.

**Hidden class mặc định.** `plainLookup` tạo hidden class từ bytecode của `Template` nhưng **không** truyền `NESTMATE`. Theo quy tắc của hidden class, quan hệ nest của nó **không lấy từ `NestHost` có sẵn trong bytecode Template**; nó có nest riêng chỉ chứa chính nó. Chúng ta **không gọi** `readHostSecret()` của lớp này, bởi bytecode tham chiếu phương thức private của host nhưng nó **không phải nestmate** của host.

**Hidden class có NESTMATE.** `nestLookup` tạo một hidden class khác, cùng bytecode nhưng chọn `NESTMATE`. Nó trở thành nestmate của `NestAccessDemo`. Do vậy phương thức `readHostSecret()` trong hidden class có thể tham chiếu `hostSecret()` private của host. `findStatic` lấy method handle, `invokeExact` gọi nó, kết quả `KEY-42`.

**Hidden không có trong `getNestMembers`.** Dù `hidden.mateHost=true`, danh sách từ `host.getNestMembers()` không ghi thêm hidden class runtime: `members.containsHidden=false`. Đây là khác biệt quan trọng giữa kiểm tra **quan hệ** và liệt kê **metadata tĩnh**.

**Primitive.** `int.class` có nest chỉ chứa chính nó theo API; `getNestHost() == int.class` là `true`. Nguyên tắc tương tự áp dụng cho array class và `void.class` khi hỏi host.

### 6.4. Vì sao hai hidden class không phải cùng một class?

Mỗi lời gọi `defineHiddenClass` tạo một hidden class có định danh runtime riêng. Dù chúng dùng cùng `byte[]` nguồn, `plain` và `hidden` là hai đối tượng `Class<?>` khác nhau, và khác `Template.class` thông thường.

- Không so sánh tên hidden class bằng chuỗi cố định: hậu tố tên runtime có thể thay đổi.
- Không dùng `Class.forName(hidden.getName())` để tìm lại hidden class; loại class này không được khám phá bằng binary name thông thường.
- Giữ tham chiếu `Class<?>` hoặc `Lookup` trả về từ lúc định nghĩa.
- `NESTMATE` quyết định quan hệ nest, không biến hidden class thành member class có khai báo trong source.

## 7. Truy cập private và `MethodHandles.Lookup`: có khác reflection không?

**Nestmate relationship** là điều kiện liên quan đến kiểm tra quyền private ở mức JVM. **Lookup** lại là đối tượng chứa quyền/capability được dùng khi tìm và gọi method handle. Hai vấn đề liên quan nhưng **không hoàn toàn tương đương**.

Ví dụ:

```java
MethodHandles.Lookup nestLookup =
        MethodHandles.lookup().defineHiddenClass(
                bytes, true,
                MethodHandles.Lookup.ClassOption.NESTMATE);
```

Lời gọi yêu cầu lookup có **full privilege access** và bytecode phù hợp package; không thể đưa bất kỳ mảng bytes hay lookup không đủ quyền nào rồi giả định JVM sẽ cấp quyền.

Sau đó:

```java
Class<?> hidden = nestLookup.lookupClass();
MethodHandle action = nestLookup.findStatic(
        hidden, "readHostSecret",
        MethodType.methodType(String.class));
```

Phương thức `findStatic` tìm thành viên với quyền của `nestLookup`. Thành viên tìm được lại chạy bytecode trong hidden class; vì hidden class là nestmate nên bytecode có thể truy cập phương thức private của host trong ví dụ.

**Không được suy luận:** “Một lớp là nestmate nên mọi đoạn code ở bất kỳ module nào đều đọc được thành viên private của nó.” Khi caller bên ngoài dùng reflection hoặc method handles, **quyền của caller**, quyền truy cập module và API được sử dụng vẫn là các yếu tố phải xét.

### Nestmate không phải quyền truy cập bừa bãi

Một số phân biệt quan trọng:

| Nội dung | Nest quyết định? | Nhận xét |
| --- | --- | --- |
| Hai runtime class có cùng host? | Có | Dùng `isNestmateOf` |
| Bytecode nestmate có thể tham chiếu private member tương ứng? | Có, dưới các quy tắc truy cập JVM | Đây là mục đích thiết kế nest-based access |
| Class ngoài nest có thể gọi private member chỉ vì cùng package? | **Không** | Package-private khác private |
| Module bên ngoài có thể tùy ý `setAccessible(true)`? | **Không** | Vẫn phải thỏa quy tắc truy cập/module của reflection |
| Hidden class có thể được tìm bằng `Class.forName`? | **Không** | Hidden không có binary name thông thường để tra cứu |
| `getNestMembers` liệt kê mọi hidden nestmate được tạo động? | **Không** | Nó phản ánh `NestMembers` tĩnh |
| `NESTMATE` tự bảo đảm bytecode hợp lệ hoặc method handle luôn thành công? | **Không** | Kiểm tra quyền, classfile, method descriptor và liên kết vẫn áp dụng |

## 8. Những điểm dễ nhầm

### 8.1. Nested class không đồng nghĩa mọi kiểu là nestmate

Trong ví dụ do `javac` tạo, member class thường là nestmate của host, nhưng **không** nên xây quy tắc “chỉ nhìn `getEnclosingClass()` là đủ”.

- `getEnclosingClass()` trả thông tin về cấu trúc khai báo bao quanh khi có.
- `getNestHost()` trả class host theo quy tắc JVM.
- `isNestmateOf(...)` kiểm tra quan hệ nest.
- `isMemberClass()` / `isLocalClass()` / `isAnonymousClass()` phân loại cấu trúc Java, không phải phép kiểm tra nest tổng quát.

Hidden class tạo qua `NESTMATE` có thể tham gia nest **không phụ thuộc** việc nó xuất hiện như nested declaration trong mã nguồn. Vì vậy, “có enclosing class” và “là nestmate” là hai đặc tính khác nhau.

### 8.2. `getNestMembers()` không phải tập hợp động

Một lỗi thiết kế thường gặp:

```java
boolean assumed =
        java.util.Arrays.asList(host.getNestMembers())
                .contains(dynamicHidden);
```

Giá trị `assumed` **có thể là `false` ngay cả khi hai class là nestmate**. Dùng:

```java
boolean correct = dynamicHidden.isNestmateOf(host);
```

Những đoạn này là snippet giả định `host` và `dynamicHidden` đã được khởi tạo thích hợp.

### 8.3. Không chỉ cần trùng tên package

Hai class có thể có chung chuỗi tên package nhưng thuộc **runtime package khác nhau** do class loader/module và ngữ cảnh JVM. Chúng không thể tự tạo quyền private qua một chuỗi tên package giống nhau. Khả năng truy cập phải tuân theo metadata nest được xác minh và các điều kiện runtime.

### 8.4. `private` không giống `protected` hay kế thừa

- `private`: được kiểm tra theo quy tắc private của class và nest. Thành viên private không tự được kế thừa theo nghĩa cho phép subclass truy cập.
- `protected`: có các quy tắc truy cập riêng liên quan package và subclass.
- Package-private: liên quan runtime package.
- Nest: là một quan hệ JVM **riêng** để hỗ trợ truy cập private.

Nếu `Child extends Parent`, điều đó **không** khiến `Child` trở thành nestmate của `Parent`. Phải kiểm tra nest độc lập.

### 8.5. Không cần học hoặc tái sử dụng synthetic accessor cũ

Một số tài liệu về Java đời cũ nhắc đến phương thức truy cập tổng hợp do compiler tạo để hỗ trợ nested class. Trên JDK hiện đại, nest-based access control đã là cơ chế chính thức. Đối với code mới, hãy dùng cú pháp Java thông thường và những API nest hiện hành; **không cần tự viết hoặc mô phỏng synthetic accessor** để hai class khai báo lồng nhau truy cập private.

## 9. Các lỗi runtime thường gặp khi thao tác nest

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `isNestmateOf(...)` trả `false` | Hai class không cùng host, hoặc một hidden class được tạo **không có `NESTMATE`** | Kiểm tra `getNestHost`, cách tạo class và tùy chọn `NESTMATE` |
| `getNestMembers()` không có hidden class vừa thêm | Danh sách API không bao gồm hidden nestmate động | Dùng `hidden.isNestmateOf(host)` |
| `getNestMembers()` có thứ tự lạ | Các phần tử sau host không có thứ tự quy định | Đừng dựa vào index sau 0; dùng so khớp phần tử |
| Bytecode tham chiếu `private` và bị `IllegalAccessError` | Quan hệ nest/điều kiện truy cập không hợp lệ lúc liên kết hoặc thực thi | Kiểm tra class file, lookup, host/member và cách tạo hidden class |
| Xác định nest lỗi khi nạp các class file không tương thích | Metadata `NestHost`/`NestMembers` không khớp hoặc classpath trộn class files sai phiên bản | Biên dịch đồng bộ các file liên quan, kiểm tra class loader/module |
| `defineHiddenClass` ném `IllegalAccessException` | Lookup không có đủ đặc quyền | Lấy đúng `Lookup` được cấp quyền theo thiết kế |
| `defineHiddenClass` lỗi package/class format | Bytecode không hợp lệ hoặc không cùng package yêu cầu | Biên dịch class mẫu đúng package, không truyền source text thay bytes |
| `getResourceAsStream(...)` trả `null` | Chưa có `NestAccessDemo$Template.class` hoặc resource không trên classpath | Biên dịch đủ file và chạy với classpath hợp lệ |
| `Class.forName(hidden.getName())` thất bại | Hidden class không có binary name dùng để tra cứu | Giữ `Lookup` hoặc `Class<?>` nhận được khi tạo |
| Không gọi được method handle | Sai tên, chữ ký, kiểu trả về hoặc quyền lookup | Kiểm tra `findStatic`, `MethodType`, quyền caller và cách gọi `invokeExact` |

Với class file do framework tạo thủ công, lỗi nest có thể xuất hiện **khi JVM kiểm tra truy cập**, không nhất thiết ngay tại dòng gọi `defineHiddenClass`. Hãy ghi nhận loại ngoại lệ, vị trí và chuỗi sự kiện thật thay vì giả định một thời điểm cố định.

## 10. Những quy tắc thiết kế an toàn khi dùng hidden nestmate

1. **Giữ một tham chiếu đáng tin cậy** tới `Lookup`/`Class<?>` mà `defineHiddenClass` trả về; không thiết kế cơ chế tìm lớp theo tên runtime.
2. **Chọn `NESTMATE` có chủ đích** khi cần cho bytecode động gọi private member của nest. Nếu không cần, tạo hidden class mặc định để giữ quan hệ nest độc lập.
3. **Không đưa bytes tùy ý từ nguồn không đáng tin** cho lookup có đặc quyền cao. Hidden class và `NESTMATE` không phải sandbox hay cơ chế xác minh an toàn bytecode đầu vào.
4. **Không suy luận quyền truy cập từ package name dạng text**. JVM kiểm tra runtime package, classfile và các điều kiện liên quan.
5. **Không dựa vào thời điểm GC/unloading của hidden class**. Tùy chọn `STRONG` điều chỉnh quan hệ vòng đời với class loader, không điều chỉnh quan hệ private/nest.
6. **Không phụ thuộc vào danh sách `getNestMembers` để quản lý các hidden class động**. Nếu framework cần quản lý chúng, tự giữ registry thích hợp trong phạm vi ứng dụng.
7. **Ưu tiên API hiện hành** thay vì thao tác class loader không chính thức hoặc tùy chỉnh các access-bridge như hướng dẫn cũ.
8. **Không dùng nest làm ranh giới bảo mật của dữ liệu**. Dù nest giúp truy cập private giữa các thành viên, cần thiết kế quyền lookup, module và nguồn bytes độc lập.

### `NESTMATE` và `STRONG` là hai quyết định khác nhau

`MethodHandles.Lookup.ClassOption` hiện có hai tùy chọn quan trọng:

- `NESTMATE`: quyết định **quan hệ nest và khả năng truy cập private**.
- `STRONG`: quyết định **quan hệ vòng đời/unloading với class loader** tương tự lớp thông thường.

Có thể dùng cả hai khi thiết kế yêu cầu, nhưng **`STRONG` không tự tạo quyền private giữa các nestmate** và **`NESTMATE` không bảo đảm hidden class sống mãi**.

## 11. Bài tập tự kiểm tra

### Bài 1. Nhận diện host và member

Cho code:

```java
class Vehicle {
    private static String id() { return "V-1"; }
    static class Engine {
        static String readId() { return id(); }
    }
}
```

Hỏi: `Vehicle.Engine.class.getNestHost() == Vehicle.class` trả gì? `Vehicle.Engine.class.isNestmateOf(Vehicle.class)` trả gì?

**Đáp án:** Cả hai là `true` khi được `javac` hiện đại biên dịch. `Engine` là thành viên cùng nest với `Vehicle`, nên có thể gọi `private static` method `id()` của host.

### Bài 2. Một class top-level ở cùng package

`Other.class` và `Vehicle.class` là hai class top-level độc lập trong cùng package, không có metadata nest kết nối chúng. Có thể cho rằng chúng là nestmate chỉ từ tên package không?

**Đáp án:** Không. Hai class cần cùng **nest host** theo cơ chế JVM; cùng package là điều kiện không đủ.

### Bài 3. Kiểm tra thành viên bằng mảng

`Vehicle.class.getNestMembers()` có bảo đảm `Engine.class` ở vị trí `[1]` không?

**Đáp án:** Không. Phần tử đầu là host nhưng thứ tự những phần tử sau không được đặc tả. Dùng `Arrays.asList(...).contains(Vehicle.Engine.class)`.

### Bài 4. Hidden class có `NESTMATE`

Một framework dùng:

```java
MethodHandles.Lookup hiddenLookup = lookup.defineHiddenClass(
        bytes, true,
        MethodHandles.Lookup.ClassOption.NESTMATE);
Class<?> H = hiddenLookup.lookupClass();
```

Nếu `lookup.lookupClass()` thuộc nest do `Vehicle.class` làm host, `H.getNestHost() == Vehicle.class` có đúng không?

**Đáp án:** Có, khi định nghĩa thành công. `NESTMATE` dùng nest host của lookup class.

### Bài 5. Vì sao không thấy hidden class trong `getNestMembers`?

`H.isNestmateOf(Vehicle.class)` là `true` nhưng `Arrays.asList(Vehicle.class.getNestMembers()).contains(H)` là `false`. Có mâu thuẫn không?

**Đáp án:** Không. `H` được thêm động; `getNestMembers()` chỉ liệt kê các thành viên được ghi trong `NestMembers` tĩnh của class file.

### Bài 6. Lớp ẩn không có `NESTMATE`

Nếu cùng bytes được định nghĩa bằng `lookup.defineHiddenClass(bytes, true)`, hidden class đó tự động có quyền gọi `Vehicle.privateMethod()` không?

**Đáp án:** Không. Mặc định nó có nest riêng. Việc bytecode nguồn từng có `NestHost` không làm nó tự gia nhập nest của lookup class; nếu bytecode cố dùng private member của host, truy cập có thể thất bại theo quy tắc JVM.

### Bài 7. Host có bắt buộc khác thành viên?

`int.class.getNestHost() == int.class` và `String.class.isNestmateOf(String.class)` có hợp lệ không?

**Đáp án:** Có. Một nest có thể chỉ gồm chính lớp/kiểu được xét, và một class luôn là nestmate của chính nó.

### Bài 8. `getEnclosingClass` và `getNestHost`

Tại sao không nên dùng `clazz.getEnclosingClass()` thay thế `clazz.getNestHost()`?

**Đáp án:** `getEnclosingClass` mô tả nguồn khai báo bao quanh; `getNestHost` phản ánh quan hệ nest JVM. Hidden nestmate động là ví dụ rõ ràng cho thấy hai khái niệm khác nhau.

## 12. Checklist, nguyên tắc QA và tài liệu

### Checklist

- [ ] Tôi hiểu **nest**, **nest host**, **nest member** và **nestmate**.
- [ ] Tôi dùng `getNestHost()` để tìm host và `isNestmateOf(...)` để kiểm tra hai class có cùng nest.
- [ ] Tôi biết phần tử đầu của `getNestMembers()` là host; các phần tử sau **không có thứ tự được bảo đảm**.
- [ ] Tôi biết nestmates theo class file dùng `NestHost`/`NestMembers` với điều kiện runtime hợp lệ.
- [ ] Tôi chứng minh được private access **hai chiều** trong ví dụ nested class.
- [ ] Tôi hiểu **cùng package**, **cùng file nguồn**, **cùng class loader** hoặc **tên chứa `$`** không đủ để kết luận là nestmate.
- [ ] Tôi biết `NESTMATE` tạo hidden class cùng nest host với lookup class.
- [ ] Tôi biết hidden nestmate động **không được liệt kê** trong `getNestMembers()`.
- [ ] Tôi hiểu vì sao hidden class mặc định (không `NESTMATE`) có nest chỉ gồm chính nó.
- [ ] Tôi phân biệt quyền truy cập private giữa nestmates với quyền `Lookup` và chính sách module.
- [ ] Tôi có thể chạy `NestAccessDemo.java` và giải thích đúng từng dòng stdout.

### Gợi ý QA code

- Dùng JDK 17+ hoặc JDK LTS hiện hành; không cần `--enable-preview`.
- Chạy biên dịch sạch `javac -encoding UTF-8 NestAccessDemo.java`, sau đó `java NestAccessDemo`.
- Nếu đọc tài nguyên lỗi, kiểm tra `NestAccessDemo$Template.class` có nằm cùng package/classpath hay không.
- Đừng hard-code tên hidden class có hậu tố động làm expected output.
- Để kiểm tra metadata class file, có thể dùng công cụ JDK `javap -v NestAccessDemo` và `javap -v 'NestAccessDemo$Member'` (cách trích dẫn dấu nháy tùy shell). Đây chỉ là cách quan sát class file tĩnh; không thể dùng `javap` trên file có sẵn để liệt kê các hidden class được tạo lúc chạy.

### Nguồn chính thức

1. [Oracle Java SE 25 — `Class` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `getNestHost`, `getNestMembers`, `isNestmateOf`, các lưu ý về hidden nestmate trong API Note.
2. [Oracle Java SE 25 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, quyền lookup, xác định host theo `NESTMATE`.
3. [Oracle Java SE 25 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
4. [JVM Specification, Java SE 25 — `NestHost` và `NestMembers`](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): cấu trúc thuộc tính class file.
5. [JVM Specification, Java SE 25 — `5.4.4 Access Control`](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4.4): kiểm tra nestmate và quyền truy cập JVM.
6. [OpenJDK JEP 181 — Nest-Based Access Control](https://openjdk.org/jeps/181): bối cảnh và thiết kế cơ chế nest chính thức từ Java 11.
7. [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): hidden class và tùy chọn nestmate đã chuẩn hóa từ Java 15.

**Tổng kết:** Nest host đại diện cho nhóm class/interface được JVM công nhận là cùng nest. `getNestHost()` tìm host; `isNestmateOf(...)` xác nhận quan hệ; `getNestMembers()` phản ánh thành viên ghi trong class file, **không liệt kê hidden nestmate được thêm động**. Nhờ nest-based access control, các nestmate hợp lệ có thể truy cập thành viên `private` của nhau. Hidden class chỉ tham gia nest của lookup class khi được tạo với `ClassOption.NESTMATE`, chứ không chỉ nhờ tên lớp, package hay metadata nest từng có trong bytes nguồn.