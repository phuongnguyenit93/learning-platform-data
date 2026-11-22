# Kiểu generic trong thông tin gỡ lỗi so với kiểu bị xóa trong bytecode (Java 10+)

## 1. Vấn đề cần hiểu

Với Java 10 trở lên, có thể viết:

```java
var names = new java.util.ArrayList<String>();
```

Trình biên dịch biết `names` có **kiểu tĩnh `ArrayList<String>`**. IDE và debugger có thể hiển thị kiểu có tham số generic `String`. Tuy nhiên, khi đọc phần **bytecode dùng để thực thi**, bạn có thể chỉ nhìn thấy kiểu `java/util/ArrayList` và lời gọi `get` trả về `Object`. Hai quan sát này **không mâu thuẫn**:

- **Ở mã nguồn và lúc biên dịch:** Java kiểm tra tham số kiểu generic như `String`. `var` nhận kiểu tĩnh của biểu thức khởi tạo; kiểm tra kiểu vẫn đầy đủ.
- **Trong các descriptor và lệnh bytecode mà JVM thực thi:** Java dùng cơ chế **type erasure** (xóa tham số kiểu). `ArrayList<String>` và `ArrayList<Integer>` đều sử dụng cùng lớp runtime `ArrayList`.
- **Trong metadata tùy chọn của file `.class`:** trình biên dịch có thể lưu **generic signature** để debugger và công cụ phân tích hiểu thêm kiểu khai báo, dù lệnh bytecode vẫn dùng kiểu đã xóa. Hai thuộc tính thường thấy là `LocalVariableTable` và `LocalVariableTypeTable`; ngoài ra còn thuộc tính `Signature` cho khai báo lớp, trường và phương thức.

Bài học này tập trung vào sự khác nhau giữa **kiểu mà Java suy luận cho `var`**, **thông tin kiểu phục vụ gỡ lỗi**, và **kiểu mà bytecode/JVM dùng khi thực thi**. Tất cả những cơ chế này vẫn áp dụng trong Java hiện nay.

## 2. `var` và generics vẫn được kiểm tra kiểu tĩnh

`var` là cú pháp **suy luận kiểu biến cục bộ**, không phải `Object`, không phải kiểu động và không tắt hệ thống generic. Ví dụ:

```java
var strings = new java.util.ArrayList<String>(); // ArrayList<String>
strings.add("Java");                              // Hợp lệ
// strings.add(100);                              // Lỗi biên dịch: không phải String
```

Trong ví dụ này, trình biên dịch biết `strings` là `ArrayList<String>` từ biểu thức `new ArrayList<String>()`. Dòng `add(100)` bị từ chối ngay cả khi chương trình chưa chạy.

Nếu vế phải là một phương thức generic, `var` nhận **kiểu trả về tĩnh của lời gọi**:

```java
var languages = java.util.List.of("Java", "Kotlin"); // List<String>
var first = languages.get(0);                       // String
```

Lời gọi `List.of` suy luận phần tử `String` từ các đối số; `var languages` nhận `List<String>`, rồi `var first` nhận `String` từ biểu thức `languages.get(0)`.

Một tình huống khác:

```java
var items = new java.util.ArrayList<>(); // ArrayList<Object>
items.add("Java");
items.add(10);
```

Ở đây diamond `<>` không có đủ ngữ cảnh cho kiểu phần tử và constructor không có đối số, nên suy ra `Object`. Đây **không phải raw type**; `ArrayList<Object>` vẫn là kiểu generic có tham số kiểu cụ thể. Không được giải thích sai rằng Java bỏ qua tham số generic của mọi biến dùng `var`.

## 3. Type erasure làm gì trong bytecode?

Theo đặc tả Java, *type erasure* ánh xạ kiểu có tham số sang kiểu không còn tham số kiểu trong descriptor thực thi:

| Kiểu trong mã Java | Kiểu sau erasure, theo cách JVM dùng trong descriptor |
| --- | --- |
| `List<String>` | `List` |
| `ArrayList<Integer>` | `ArrayList` |
| `Map<String, Integer>` | `Map` |
| `T` với `T` không có upper bound riêng | `Object` |
| `T extends Number` | `Number` (erasure của bound đầu tiên) |

Đây là quy tắc cho **kiểu/descriptor phục vụ thực thi**. Nó **không có nghĩa** mọi chuỗi ký tự mô tả generic đều biến mất khỏi file `.class`: compiler vẫn có thể ghi *signature metadata* ở các thuộc tính khác. Cần phân biệt **descriptor đã erasure** với **generic signature mang tính metadata**.

### 3.1. JVM không tạo một lớp riêng cho từng kiểu phần tử

```java
var strings = new java.util.ArrayList<String>();
var numbers = new java.util.ArrayList<Integer>();

System.out.println(strings.getClass() == numbers.getClass()); // true
```

`strings` có kiểu tĩnh `ArrayList<String>` và `numbers` có kiểu tĩnh `ArrayList<Integer>`, nhưng cả hai đối tượng đều là instance của cùng **lớp runtime `java.util.ArrayList`**. Không có hai lớp runtime tên `ArrayList<String>` và `ArrayList<Integer>`.

### 3.2. Trình biên dịch có thể thêm `checkcast`

Xét:

```java
var names = new java.util.ArrayList<String>();
names.add("Java");
var first = names.get(0); // first có kiểu String
```

Chữ ký sử dụng ở mức bytecode của `ArrayList.get(int)` trả về `Object`, tức dạng descriptor `(I)Ljava/lang/Object;`. Để sử dụng kết quả với kiểu tĩnh `String`, trình biên dịch có thể sinh lệnh `checkcast java/lang/String`. Ví dụ biên dịch cụ thể ở phần sau minh họa lệnh này xuất hiện.

**Điểm quan trọng:** việc có lệnh cast sau erasure không biến `var` thành kiểu động. Trình biên dịch đã kiểm tra generic trước đó. Nếu một chương trình dùng raw type hoặc unchecked conversion khiến dữ liệu sai kiểu lọt vào collection, thao tác đọc và cast có thể ném `ClassCastException` lúc chạy. Với mã generic được kiểm tra an toàn, loại lỗi đó được ngăn từ lúc biên dịch ở những chỗ có đủ thông tin kiểu.

## 4. Ba nơi chứa thông tin kiểu trong file `.class`

Để đọc kết quả `javap -v`, hãy tách biệt ba cấu trúc sau.

| Thành phần | Thông tin chính | Vai trò |
| --- | --- | --- |
| **Descriptor** của field/method và lệnh bytecode | Kiểu JVM đã erasure, ví dụ `Ljava/util/List;` hoặc `(I)Ljava/lang/Object;` | Được dùng cho liên kết phương thức, xác minh và thực thi |
| **`LocalVariableTable` (LVT)** | Tên biến cục bộ, phạm vi theo bytecode offset, slot và descriptor, ví dụ `names Ljava/util/ArrayList;` | Metadata tùy chọn để công cụ gỡ lỗi tìm biến cục bộ |
| **`LocalVariableTypeTable` (LVTT)** | Thông tin *generic signature* cho biến cục bộ có kiểu generic/type variable, ví dụ `names Ljava/util/ArrayList<Ljava/lang/String;>;` | Metadata tùy chọn để debugger thấy tham số generic |
| **`Signature`** | Chữ ký generic của các khai báo như field, method, class, ví dụ tham số phương thức `List<String>` | Công cụ và reflection có thể đọc một phần thông tin generic được khai báo |

**Phân biệt hai cách viết kiểu JVM:**

- `Ljava/util/List;` là **descriptor** của kiểu tham chiếu `java.util.List` đã erasure.
- `Ljava/util/List<Ljava/lang/String;>;` là **generic signature** có chứa đối số kiểu `String`.
- Dấu `L` bắt đầu mô tả một kiểu tham chiếu trong cú pháp JVM, dấu `;` kết thúc kiểu; dấu `/` phân tách package trong tên nội bộ. Cú pháp này không phải mã Java thông thường và không phải tên lớp runtime mới.

### 4.1. `LocalVariableTable`

`LocalVariableTable` thường chứa tên biến, vị trí trong bảng biến cục bộ (slot), phạm vi hiệu lực theo chỉ số bytecode, và descriptor của biến. Chẳng hạn:

```text
LocalVariableTable:
  Start  Length  Slot  Name   Signature
      9      49     1 names   Ljava/util/ArrayList;
```

Cột có nhãn `Signature` trong **bảng hiển thị của `javap`** ở đây chứa **descriptor `Ljava/util/ArrayList;`**. Không nên kết luận rằng LVT đã giữ lại `<String>` chỉ vì tiêu đề cột là `Signature`.

### 4.2. `LocalVariableTypeTable`

Với biến generic, compiler có thể ghi thêm:

```text
LocalVariableTypeTable:
  Start  Length  Slot  Name   Signature
      9      49     1 names   Ljava/util/ArrayList<Ljava/lang/String;>;
```

Hai dòng cùng nói về biến `names` ở một vị trí/slot tương ứng, nhưng LVTT cung cấp kiểu có tham số `String`. Theo đặc tả JVM, LVTT dành cho **generic signature của biến cục bộ**; với biến không có kiểu tham số hoặc type variable, thông thường chỉ có dòng trong LVT.

**Các bảng này là metadata tùy chọn**: trình biên dịch hoặc cấu hình build có thể không ghi chúng. Debugger đôi khi hiển thị ít thông tin hơn nếu thiếu metadata, nhưng mã bytecode vẫn chạy theo quy tắc kiểu Java/JVM như cũ.

### 4.3. Thuộc tính `Signature` độc lập với debug info của biến cục bộ

Ví dụ khai báo:

```java
static void show(java.util.List<String> words) {
    // ...
}
```

Descriptor phương thức mà JVM dùng là:

```text
(Ljava/util/List;)V
```

Nhưng file `.class` có thể chứa thuộc tính `Signature`:

```text
(Ljava/util/List<Ljava/lang/String;>;)V
```

`V` nghĩa là phương thức trả về `void`. **`Signature` của phương thức không phải `LocalVariableTypeTable`**: đó là metadata của *khai báo phương thức*, phục vụ đọc thông tin generic trong class file và các API reflection thích hợp. Vì vậy, câu nói “type erasure xóa toàn bộ dấu vết generic khỏi mọi chỗ trong class file” là không chính xác.

## 5. Chương trình Java 17+ hoàn chỉnh để kiểm chứng

Lưu mã sau trong file **`GenericDebugDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericDebugDemo {
    static void show(List<String> words) {
        // Kiểu tĩnh suy luận: ArrayList<String>.
        var names = new ArrayList<>(words);

        // Kiểu tĩnh suy luận: String.
        var first = names.get(0);

        // Có thể sử dụng cùng kết quả dưới kiểu Object.
        Object rawView = names.get(0);

        System.out.println("first=" + first.toUpperCase());
        System.out.println(
                "runtimeElement=" + rawView.getClass().getSimpleName()
        );
    }

    public static void main(String[] args) {
        show(List.of("java", "bytecode"));

        var strings = new ArrayList<String>();
        var numbers = new ArrayList<Integer>();

        System.out.println(
                "sameClass=" + (strings.getClass() == numbers.getClass())
        );
    }
}
```

Biên dịch với **đầy đủ thông tin debug** rồi chạy:

```bash
javac -encoding UTF-8 -g GenericDebugDemo.java
java GenericDebugDemo
```

**Kết quả stdout chính xác:**

```text
first=JAVA
runtimeElement=String
sameClass=true
```

Giải thích:

1. `new ArrayList<>(words)` dựa vào đối số `List<String>` để suy ra kiểu `ArrayList<String>`. `var names` giữ kiểu tĩnh đó.
2. `names.get(0)` có kiểu tĩnh `String`; `toUpperCase()` cho `JAVA`.
3. `rawView` được khai báo `Object` nhưng đối tượng thực tế là `String`, nên `getClass().getSimpleName()` in `String`. Việc gọi `getClass()` xem lớp runtime của **phần tử**, không xem tham số kiểu generic của `ArrayList`.
4. Hai biến `strings`, `numbers` khác kiểu tham số generic khi biên dịch nhưng cùng lớp runtime `ArrayList`, nên `sameClass=true`.

Ví dụ này sử dụng các tính năng Java ổn định từ Java 10 trở đi và chạy trên JDK 17+. Không cần bật preview.

## 6. Dùng `javap` để quan sát bytecode và metadata

Sau khi chạy `javac -g`, dùng công cụ chuẩn của JDK:

```bash
javap -v -p GenericDebugDemo
```

Tùy chọn `-v` in thông tin chi tiết về constant pool, code, descriptor và các thuộc tính class file; `-p` cho hiển thị cả thành viên không public. Có thể thêm `-c -l` để yêu cầu rõ phần lệnh và bảng biến, dù `-v` đã hiển thị nhiều thông tin tương ứng.

**Trích đoạn tiêu biểu** từ lớp biên dịch bằng `javac -g` (đã rút gọn và bỏ các dòng không liên quan; **offset và chỉ số constant pool có thể khác theo JDK/compiler**):

```text
static void show(java.util.List<java.lang.String>);
  descriptor: (Ljava/util/List;)V
  ...
  invokevirtual ... // Method java/util/ArrayList.get:(I)Ljava/lang/Object;
  checkcast     ... // class java/lang/String
  ...
  LocalVariableTable:
    Start  Length  Slot  Name   Signature
        0      58     0 words   Ljava/util/List;
        9      49     1 names   Ljava/util/ArrayList;
       18      40     2 first   Ljava/lang/String;
  LocalVariableTypeTable:
    Start  Length  Slot  Name   Signature
        0      58     0 words   Ljava/util/List<Ljava/lang/String;>;
        9      49     1 names   Ljava/util/ArrayList<Ljava/lang/String;>;
  Signature: ... // (Ljava/util/List<Ljava/lang/String;>;)V
```

Hãy đọc từng phần theo thứ tự:

- **`descriptor: (Ljava/util/List;)V`:** JVM nhìn thấy một tham số kiểu `List` đã erasure và kiểu trả về `void`; phần `<String>` không nằm trong descriptor.
- **`invokevirtual ... get:(I)Ljava/lang/Object;`:** lệnh gọi `ArrayList.get` trả về `Object` ở mức descriptor bytecode.
- **`checkcast ... String`:** compiler thêm kiểm tra/cast khi chuyển kết quả generic đã erasure thành kiểu tĩnh `String`.
- **LVT của `words` và `names`:** chỉ ghi `List` và `ArrayList` ở descriptor.
- **LVTT của chính những biến đó:** có tham số kiểu `String`. Đây là nguồn metadata giúp công cụ gỡ lỗi hiển thị kiểu generic.
- **`Signature` ở phương thức:** lưu chữ ký generic `List<String>` của tham số đã khai báo, **khác** LVTT của biến cục bộ.

Trong `main`, nếu xem các bảng debug, bạn cũng sẽ thấy `strings` và `numbers` có cùng descriptor `Ljava/util/ArrayList;` nhưng hai signature khác nhau: `Ljava/util/ArrayList<Ljava/lang/String;>;` và `Ljava/util/ArrayList<Ljava/lang/Integer;>;`. Đây là cách đối chiếu trực tiếp thông tin gỡ lỗi với type erasure.

## 7. Tác động của tùy chọn biên dịch debug

`LocalVariableTable` và `LocalVariableTypeTable` phụ thuộc vào thông tin debug mà compiler phát ra. Với **`javac` hiện hành**:

| Lệnh biên dịch | Thông tin biến cục bộ trong class file |
| --- | --- |
| `javac -g GenericDebugDemo.java` | Yêu cầu toàn bộ thông tin debug, bao gồm biến cục bộ; trong ví dụ sẽ có LVT và LVTT |
| `javac -g:vars GenericDebugDemo.java` | Yêu cầu debug info cho các biến cục bộ |
| `javac GenericDebugDemo.java` | Mặc định có thông tin dòng và file nguồn, **không mặc định ghi đầy đủ thông tin biến cục bộ** |
| `javac -g:none GenericDebugDemo.java` | Không ghi các thuộc tính debug tương ứng; LVT/LVTT sẽ không hiện trong ví dụ |

Thử biên dịch lại sau khi đã quan sát bản `-g`:

```bash
javac -encoding UTF-8 -g:none GenericDebugDemo.java
javap -v -p GenericDebugDemo
```

Lúc này các bảng LVT/LVTT biến mất khỏi ví dụ, nhưng **descriptor bytecode vẫn dùng kiểu đã erasure**, và **`Signature` của phương thức `show(List<String>)` vẫn có thể tồn tại**, vì thuộc tính `Signature` không phải là bảng debug biến cục bộ được điều khiển bởi `-g`. Điều này đã được kiểm chứng cả với `javac --release 17`.

**Không nhầm `-parameters` với `-g:vars`:** tùy chọn `-parameters` nhằm lưu tên tham số hình thức của phương thức/constructor cho reflection; nó không thay thế việc ghi local variable debug tables. Việc có/không có `-g` không thay đổi kiểu tĩnh trong chương trình nguồn hay quy tắc type erasure.

## 8. Debugger có thể thấy gì, và reflection có thể thấy gì?

### 8.1. Khi debug một biến `var` có generic

Nếu class được biên dịch có metadata phù hợp, debugger có thể đọc LVTT và thể hiện kiểu được suy ra như `ArrayList<String>`. Đây là **thông tin biên dịch được ghi trong file `.class`**, không phải bằng chứng JVM tạo một lớp runtime `ArrayList<String>` riêng biệt.

Khả năng hiển thị còn phụ thuộc công cụ debugger, compiler, các thuộc tính class file có mặt và vị trí dừng. Vì LVT/LVTT là tùy chọn, **không được mặc định rằng mọi build hoặc mọi debugger đều hiển thị chính xác type argument của biến cục bộ**.

### 8.2. Java reflection và metadata generic của khai báo

Java reflection có thể đọc một số generic signature **được khai báo trên field, phương thức và lớp**. Chẳng hạn, với `show(List<String> words)` ở ví dụ trên, `Method.getGenericParameterTypes()` có thể cho biết tham số khai báo là `List<String>`, nhờ metadata `Signature` của phương thức.

Tuy nhiên, API reflection chuẩn **không có API thông thường để liệt kê từng biến cục bộ trong thân phương thức và hỏi generic type của nó**. Thông tin generic của local variable có thể được công cụ debugger hoặc bytecode parser đọc từ LVTT nếu bảng đó hiện diện.

Cũng không thể làm:

```java
// Ví dụ cố ý sai: kiểu List<String> không phải reifiable tại runtime.
// if (value instanceof java.util.List<String>) { ... }
```

Nếu chỉ cần biết một đối tượng có phải `List` hay không, có thể kiểm tra `instanceof List<?>` hoặc `instanceof List` theo ngữ cảnh, nhưng **đó không xác thực các phần tử thực tế đều là `String`**. Kiểu generic `List<String>` là ràng buộc tĩnh; không tồn tại phép kiểm tra tự động toàn bộ tham số kiểu ấy tại runtime.

### 8.3. Vì sao `Class.getTypeParameters()` không cho biết `ArrayList<String>`?

`ArrayList.class.getTypeParameters()` cho biết lớp `ArrayList` **khai báo** tham số kiểu như `E`, chứ không cho biết một instance cụ thể đã được tạo theo `ArrayList<String>` hay `ArrayList<Integer>`. `strings.getClass()` chỉ trả về đối tượng `Class` tương ứng với lớp runtime `ArrayList`.

Cần phân biệt **generic declaration** (có thể còn metadata `Signature`) với **generic instantiation của đối tượng runtime** (phần lớn đã erasure).

## 9. Các ngộ nhận và lỗi thường gặp

**Ngộ nhận 1: “`var` làm mất kiểu generic.”**  
Sai. `var` nhận kiểu tĩnh của biểu thức khởi tạo. Ví dụ `var xs = new ArrayList<String>();` vẫn được kiểm tra như `ArrayList<String>`. Erasure xảy ra khi biểu diễn generic sang bytecode, dù khai báo nguồn có dùng `var` hay kiểu tường minh.

**Ngộ nhận 2: “Trong `javap` chỉ thấy `ArrayList` nên compiler không biết `String`.”**  
Sai. Kiểu `String` đã tham gia kiểm tra lúc biên dịch. Descriptor JVM có erasure; bảng LVTT có thể giữ lại signature `ArrayList<String>` để gỡ lỗi.

**Ngộ nhận 3: “Metadata trong LVTT khiến JVM tự kiểm tra phần tử `String`.”**  
Sai. LVTT là metadata tùy chọn. JVM thực thi bytecode theo các descriptor và lệnh kiểm tra/cast; LVTT không biến `ArrayList<String>` thành một lớp runtime riêng.

**Ngộ nhận 4: “Tắt `-g` sẽ xóa hết thông tin generic của toàn class file.”**  
Sai. `-g:none` tắt debug tables, nhưng thuộc tính `Signature` của khai báo generic như `show(List<String>)` vẫn có thể được phát ra. Cần xem đúng loại thuộc tính trước khi kết luận.

**Ngộ nhận 5: “Có `checkcast` là `var` động hoặc generic không an toàn.”**  
Sai. `checkcast` là một phần của cách compiler thực hiện type erasure và giữ các giả định kiểu ở vị trí cần thiết. Bản thân `var` vẫn là cú pháp kiểu tĩnh.

**Ngộ nhận 6: “`new ArrayList<>()` trong `var` luôn suy ra `String` nếu sau đó thêm chuỗi.”**  
Sai. Khi constructor không có đối số và không có target type cụ thể, `var xs = new ArrayList<>();` thường suy ra `ArrayList<Object>`. Muốn kiểu `String` hãy viết `new ArrayList<String>()` hoặc `List<String> xs = new ArrayList<>();`. Đây là vấn đề suy luận generic ở **mã nguồn**, khác với erasure.

## 10. Quy trình thực hành khi phân tích lỗi generic

1. **Kiểm tra kiểu tĩnh ở mã nguồn:** biểu thức bên phải `var` có kiểu gì? Diamond `<>` có đủ ngữ cảnh để suy ra type argument mong muốn không?
2. **Biên dịch có thông tin biến cục bộ:** dùng `javac -g` hoặc `javac -g:vars` nếu cần debugger thấy tên/kiểu generic của local variables.
3. **Dùng `javap -v -p` trên đúng file `.class`:** đọc descriptor và các lệnh bytecode trước, sau đó mới đối chiếu LVT, LVTT và `Signature`.
4. **Đọc đúng mục đích của từng thông tin:** descriptor thể hiện kiểu JVM dùng để thực thi; LVTT thể hiện generic signature phục vụ công cụ; `Signature` của phương thức/lớp/trường thể hiện một phần khai báo generic.
5. **Nếu gặp `ClassCastException`:** kiểm tra những chỗ raw type, unchecked cast, reflection hay dữ liệu không được bảo đảm kiểu. Đừng quy nguyên nhân cho riêng `var` hoặc vì metadata debugger thiếu.
6. **Khi cần truyền đạt ý định rõ ràng:** khai báo `List<String> xs = new ArrayList<>();` giúp thể hiện kiểu giao diện, còn `var xs = new ArrayList<String>();` cho kiểu tĩnh `ArrayList<String>`. Chọn theo hợp đồng và khả năng đọc hiểu mã.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `var names = new ArrayList<String>();` có cho phép `names.add(42)` không, dù bytecode chứa `ArrayList` không có `String`?  
**Đáp án:** Không. Java từ chối ở thời điểm biên dịch vì kiểu tĩnh của `names` là `ArrayList<String>`. Erasure của bytecode không làm mất kiểm tra kiểu nguồn.

**Câu 2.** Trong `javap`, `LocalVariableTable` hiển thị `Ljava/util/List;`, còn `LocalVariableTypeTable` hiển thị `Ljava/util/List<Ljava/lang/String;>;`. Hai dòng có phải mô tả hai biến khác nhau không?  
**Đáp án:** Không nhất thiết. Chúng có thể mô tả **cùng một biến**: LVT cung cấp descriptor đã erasure, LVTT cung cấp generic signature bổ sung.

**Câu 3.** Chạy `javac -g:none` có làm `List<String>` biến thành `List<Object>` ở thời điểm biên dịch không?  
**Đáp án:** Không. Tùy chọn chỉ thay đổi debug information được ghi ra; kiểu tĩnh và quy tắc generics của mã nguồn không đổi.

**Câu 4.** Vì sao `ArrayList.get(int)` trả `Object` ở mức bytecode nhưng `var first = names.get(0);` vẫn có kiểu `String`?  
**Đáp án:** Generic API được kiểm tra theo `ArrayList<String>` lúc biên dịch; sau erasure, lời gọi có descriptor trả `Object` và compiler có thể thêm `checkcast String` trước khi dùng kết quả như `String`.

**Câu 5.** Reflection có thể đọc `List<String>` của tham số đã khai báo trong phương thức, vậy có thể dùng `getClass()` để biết type argument `String` của một instance `ArrayList<String>` không?  
**Đáp án:** Không. Reflection đọc metadata generic của **khai báo** qua `Signature` trong những trường hợp phù hợp; `getClass()` của instance chỉ cho biết lớp runtime `ArrayList`.

## 12. Ghi nhớ

- `var` suy ra **kiểu tĩnh đầy đủ**, kể cả tham số generic, từ biểu thức khởi tạo. Java vẫn kiểm tra kiểu tại thời điểm biên dịch.
- **Type erasure** làm descriptor và mã JVM thực thi dùng kiểu đã erasure, chẳng hạn `List` thay cho `List<String>`; compiler có thể thêm `checkcast` khi cần.
- **`LocalVariableTable`** giữ descriptor của biến cục bộ; **`LocalVariableTypeTable`** có thể giữ generic signature của cùng biến để debugger hiểu `<String>`.
- **`Signature`** của lớp, trường, phương thức là loại metadata khác, có thể còn tồn tại dù **`-g:none`** làm biến mất bảng debug của local variables.
- Metadata generic **không tái tạo một kiểu runtime riêng cho mỗi tham số kiểu**. Hai đối tượng `ArrayList<String>` và `ArrayList<Integer>` cùng có lớp runtime `ArrayList`.
- Khi phân tích bytecode, hãy xem **descriptor, lệnh cast và debug/signature metadata** như ba mảnh thông tin bổ sung, không thay thế nhau.

## Tài liệu tham khảo chính thức

- OpenJDK JEP 286 — Local-Variable Type Inference (Java 10): https://openjdk.org/jeps/286
- Java Language Specification (Java SE 25), `4.6 Type Erasure và `4.7 Reifiable Types: https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html
- Java Virtual Machine Specification (Java SE 25), `4.7.13 LocalVariableTable, `4.7.14 LocalVariableTypeTable, `4.7.9 Signature: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html
- Java SE 25 Tools — `javac`, các tùy chọn `-g`, `-g:vars` và `-g:none`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- Java SE 25 Tools — `javap`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html
