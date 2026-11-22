# Phép nối chuỗi qua `StringConcatFactory` và `invokedynamic`

## 1. Bức tranh tổng quan

Java cho phép nối chuỗi rất tự nhiên bằng toán tử `+`:

```java
String name = "Java";
int version = 17;
String description = "Language: " + name + ", version=" + version;
```

Đây là đoạn mã minh họa trong thân phương thức. Giá trị cuối cùng là `Language: Java, version=17`. Cú pháp `+` là một phần **ngôn ngữ Java**, còn cách trình biên dịch tạo bytecode để thực thi phép nối là một quyết định triển khai.

Từ **Java 9**, theo hướng thay đổi của **JEP 280 (Indify String Concatenation)**, trình biên dịch `javac` thường biểu diễn các phép nối `String` động bằng lệnh bytecode **`invokedynamic`**. Khi liên kết lời gọi đó, JVM sử dụng bootstrap method thuộc lớp **`java.lang.invoke.StringConcatFactory`** để xây dựng cơ chế nối phù hợp với kiểu đối số và hằng số của phép nối.

Các khái niệm cần tách biệt:

- `String` vẫn **bất biến (immutable)**: biểu thức nối tạo giá trị chuỗi kết quả theo ngữ nghĩa ngôn ngữ.
- `+` vẫn là cú pháp Java; lập trình viên không cần gọi `StringConcatFactory`.
- `invokedynamic` là **lệnh bytecode** liên kết lời gọi thông qua một bootstrap method, không phải câu lệnh Java mới hay việc tìm tên hàm bằng reflection mỗi lần chạy.
- `StringConcatFactory` là **cơ sở hạ tầng runtime** cho việc xây dựng lời gọi nối chuỗi; không phải định dạng dữ liệu hay kho lưu trữ chuỗi.

Với trường hợp chỉ gồm các hằng chuỗi, `javac` có thể gộp giá trị ngay khi biên dịch và không cần `invokedynamic` cho chính phép nối đó. Vì vậy cần nhìn bytecode của **trường hợp cụ thể**, thay vì khẳng định mọi dấu `+` đều trở thành `invokedynamic`.

## 2. Trước Java 9: phép nối thường thành `StringBuilder`

Một ví dụ đơn giản:

```java
public class Contrast {
    public static String render(String name, int n) {
        return "Name=" + name + ", count=" + n;
    }
}
```

Khi biên dịch mã này bằng `javac --release 8`, bytecode có thể chứa chuỗi thao tác tương đương:

```text
new           java/lang/StringBuilder
invokespecial java/lang/StringBuilder.<init>
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.append
invokevirtual java/lang/StringBuilder.toString
```

Trong kết quả thực tế, bytecode còn chứa các lệnh nạp đối số và có thể chọn overload `append(String)`, `append(int)`. Đoạn trên là **lược trích những thao tác chính**, không phải toàn bộ bản disassembly nguyên văn.

Cách cũ giúp nối hiệu quả hơn việc tạo một chuỗi riêng cho mỗi cặp toán hạng. Nhưng nó cũng ràng buộc chiến lược nối vào bytecode do compiler phát ra. Muốn thay đổi toàn bộ chiến lược, JVM/JIT phải nhận diện và tối ưu mẫu bytecode `StringBuilder` tương ứng.

## 3. Từ Java 9: `invokedynamic` tách ý nghĩa nối khỏi chiến lược thực thi

Cũng với lớp `Contrast` trên, khi biên dịch `javac --release 17`, `javap -c` cho thấy một lệnh dạng:

```text
invokedynamic #... // makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
```

Đây là **trích đoạn mô tả dạng output**; số index constant pool phụ thuộc file class được biên dịch. Tham số `String` và `int` trong chữ ký cho biết lời gọi xử lý các giá trị động loại đó; các phần như `Name=` và `, count=` có thể được đưa vào recipe làm hằng. Khi quan sát lệnh này, không có nghĩa Java đã bỏ bất biến của `String` hay chuyển thành nối chuỗi ở thời điểm biên dịch: nó chỉ thay đổi **cách gọi logic nối ở runtime**.

Luồng khái quát:

```text
Mã Java: "Name=" + name + ", count=" + n
          |
          v
javac (target Java 9+)
          |
          v
Class file: invokedynamic + BootstrapMethods + recipe/metadata
          |
          v
JVM liên kết invokedynamic với StringConcatFactory
          |
          v
CallSite / MethodHandle có kiểu phù hợp
          |
          v
Runtime thực thi phép nối với đối số hiện tại
          |
          v
String kết quả
```

**JVM có thể tối ưu và JIT có thể inline** lời gọi được liên kết. Từ một instruction `invokedynamic` trong class file, không thể kết luận chính xác mỗi lần chạy tạo bao nhiêu đối tượng, cấp phát bao nhiêu mảng byte hay chạy bao nhiêu lệnh máy: đó là chuyện tối ưu runtime của JVM cụ thể.

## 4. Bootstrap method và cơ chế liên kết call site

`invokedynamic` có entry trong constant pool, mô tả tên lời gọi, kiểu hàm (tham số và kiểu trả về) cùng thông tin về **bootstrap method**. Khi JVM cần liên kết instruction, bootstrap method được gọi với ngữ cảnh liên kết và các hằng static liên quan, rồi trả về một `CallSite` có target phù hợp.

Trong tình huống nối chuỗi được `javac` tạo ra, bootstrap phổ biến là:

- `StringConcatFactory.makeConcat(...)`: cung cấp dạng nối dựa trên các đối số động.
- `StringConcatFactory.makeConcatWithConstants(...)`: nhận thêm một **recipe** và các hằng bootstrap, nhờ đó có thể trộn văn bản cố định với các giá trị động.

Các phương thức này thuộc API `java.lang.invoke`. `javac` thường chọn `makeConcatWithConstants` trong các bản JDK hiện đại; chi tiết cụ thể có thể thay đổi theo phiên bản compiler, lựa chọn target, ngữ cảnh mã và các tối ưu.

Ở dạng `makeConcatWithConstants`, **recipe** có thể chứa hai marker điều khiển:

| Marker trong recipe | Ý nghĩa |
| --- | --- |
| `\u0001` | Đặt một giá trị từ các đối số động của lời gọi nối |
| `\u0002` | Đặt một hằng từ các static bootstrap constants |
| Ký tự khác | Đoạn văn bản cố định được đưa trực tiếp vào kết quả |

Ví dụ, recipe được `javap -v` in gần như `Xin chào \u0001 \u0001 / \u0001` là cấu trúc ghép chuỗi với ba giá trị động ở ba vị trí. Marker `\u0001` trong disassembly là ký hiệu cho **một ký tự điều khiển**, không phải sáu ký tự văn bản cần xuất hiện trong output người dùng. Không nên tự xây dựng recipe bằng cách nối các đoạn tùy ý rồi kỳ vọng mọi implementation có chiến lược giống nhau.

**Liên kết call site** không đồng nghĩa “phân tích lại biểu thức `+` từ mã nguồn ở mỗi lần thực thi”. JVM liên kết instruction với target; các lần thực thi sau gọi target đó theo cơ chế của JVM, còn compiler runtime có thể tối ưu thêm. Thời điểm liên kết thường là khi site được sử dụng lần đầu, song mã nên dựa vào **ngữ nghĩa Java**, không dựa vào một lịch liên kết tuyệt đối.

## 5. Ví dụ chạy được với Java 17+

Tạo file `ConcatIndyDemo.java`:

```java
public class ConcatIndyDemo {
    static String mark(String name, String value) {
        System.out.println("eval " + name);
        return value;
    }

    public static void main(String[] args) {
        String who = "Java";
        int version = 17;
        Object absent = null;
        String message = "Xin chào " + who + " " + version + " / " + absent;
        System.out.println("message = " + message);

        String order = mark("left", "A") + mark("right", "B") + 7;
        System.out.println("order = " + order);

        String folded = "foo" + "bar";
        System.out.println("folded = " + folded);

        String explicit = new StringBuilder()
                .append(who)
                .append("!")
                .toString();
        System.out.println("builder = " + explicit);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ConcatIndyDemo.java
java ConcatIndyDemo
```

Kết quả chuẩn đã được đối chiếu khi chạy chương trình:

```text
message = Xin chào Java 17 / null
eval left
eval right
order = AB7
folded = foobar
builder = Java!
```

Giải thích các chi tiết đáng chú ý:

1. Giá trị `null` trong biểu thức nối chuỗi được chuyển thành văn bản `"null"` theo ngữ nghĩa string conversion của Java. Không thể đồng nhất việc nối bằng `+` với gọi trực tiếp `someString.concat(null)`, vì phương thức `concat` nhận đối số `null` có thể gây `NullPointerException`.
2. Hai lời gọi `mark` được đánh giá **từ trái sang phải**, mỗi lời gọi một lần. Đổi chiến lược bytecode sang `invokedynamic` không được phép đảo hiệu ứng phụ của toán hạng. Vì vậy console in `eval left` rồi `eval right`.
3. `mark("left", "A") + mark("right", "B") + 7` cho `AB7` vì khi phép cộng đã ở chế độ nối chuỗi, số `7` được chuyển thành ký tự theo quy tắc nối. Literal số `7` có thể được compiler đưa vào recipe thay vì thành đối số động riêng.
4. `"foo" + "bar"` là **biểu thức hằng**; `javac` gộp thành `"foobar"` ngay trong class file. Phần in `"folded = " + folded` trong ví dụ vẫn có thể là một site `invokedynamic` riêng vì `folded` là local variable thường, không phải một hằng compile-time variable được khai báo `final`.
5. Đoạn `new StringBuilder(...).append(...).toString()` là cách xây dựng chuỗi tường minh. Nó vẫn hợp lệ ở Java mới; compiler không buộc lập trình viên viết nó để nối một biểu thức `+` thông thường.

## 6. Dùng `javap` để tự nhìn chứng cứ bytecode

Sau khi biên dịch, chạy:

```bash
javap -c -v ConcatIndyDemo
```

Trong kết quả, tập trung vào ba vị trí:

**A. Lệnh trong phần `Code`:** Một lệnh có dạng:

```text
invokedynamic #... // makeConcatWithConstants:(Ljava/lang/String;ILjava/lang/String;)Ljava/lang/String;
```

Đây là phép nối `message` của ví dụ, có các đối số động dạng `String`, `int`, `String` (Javac có thể chuyển `Object absent` thành `String` trước khi gọi site). Các chuỗi cố định `Xin chào` và dấu phân cách có thể nằm trong recipe.

**B. Phần `BootstrapMethods`:** Trong `javap -v`, ta có thể thấy bootstrap handle trỏ đến:

```text
REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants
```

Cùng với các method arguments dạng recipe, ví dụ `Xin chào \u0001 \u0001 / \u0001`. Thứ tự và constant-pool indices được JVM/class file xác định và có thể khác nếu thay mã hoặc compiler.

**C. Biểu thức hằng:** Đối với `String folded = "foo" + "bar";`, `javap` có thể hiển thị:

```text
ldc #... // String foobar
```

`ldc` nạp một hằng từ constant pool. Đây là bằng chứng phép nối *hai chuỗi hằng* được giải quyết tại compile time; không có site nối riêng cho biểu thức đó. Nếu nhìn thấy `invokedynamic` ở dòng in `folded`, đó là phép nối khác: `"folded = " + folded`.

Để so sánh rõ cơ chế cũ/mới, tạo file `Contrast.java` như ở phần 2 rồi biên dịch thành **hai thư mục output khác nhau**:

```bash
javac --release 8 -d out8 Contrast.java
javac --release 17 -d out17 Contrast.java
javap -classpath out8 -c Contrast
javap -classpath out17 -c Contrast
```

Tạo sẵn các thư mục `out8` và `out17` nếu hệ thống biên dịch yêu cầu. Với compiler `javac` đã kiểm thử, bản target 8 dùng `StringBuilder.append`, còn target 17 dùng `invokedynamic`. Lệnh `--release 8` biên dịch một class tương thích API/bytecode Java 8; nó không bắt buộc bạn thực sự phải cài JDK 8 để quan sát output, miễn JDK hiện tại còn hỗ trợ release đó.

**Quan trọng:** `javap` cho thấy chiến lược do trình biên dịch phát ra ở class file. Nó **không phải phép đo thời gian thực thi** và không hiển thị toàn bộ mã máy mà JIT chọn sau khi chương trình chạy nóng.

## 7. Ngữ nghĩa biểu thức `+` không đổi

Dù bytecode được tạo theo kiểu nào, chương trình Java vẫn phải tuân thủ ngữ nghĩa của toán tử `+`:

### Phân biệt cộng số và nối chuỗi

```java
String a = 1 + 2 + "x";    // "3x"
String b = "x" + 1 + 2;    // "x12"
String c = "x" + (1 + 2);  // "x3"
```

Toán tử `+` kết hợp từ trái sang phải. Trước khi xuất hiện toán hạng `String`, phép `1 + 2` là cộng số. Khi đã là nối chuỗi, các giá trị tiếp theo được chuyển thành văn bản. Dùng dấu ngoặc để tránh lỗi logic thay vì trông cậy vào chi tiết tối ưu bytecode.

### Thứ tự và ngoại lệ của toán hạng

```java
String s = first() + second() + third();
```

Ba lời gọi (nếu trả về kiểu phù hợp) phải được đánh giá theo thứ tự Java quy định; các tác dụng phụ và ngoại lệ quan sát được không được phép bị thay đổi chỉ vì compiler dùng `invokedynamic`. Không thể “tối ưu” bằng cách bỏ một lời gọi có tác dụng phụ.

### Hằng gộp trước, runtime chỉ xử lý phần cần thiết

```java
String compileTime = "ab" + "cd"; // "abcd"
String runtime = prefix + "cd";   // phụ thuộc prefix
```

Với biểu thức hoàn toàn là hằng, compiler có thể gộp chuỗi. Với `prefix` là biến có giá trị runtime, cần thực hiện phép nối khi chạy (dưới dạng `invokedynamic` hoặc chiến lược khác của compiler).

### `null` và chuyển kiểu thành String

Khi nối một đối tượng (kể cả `null`), Java áp dụng string conversion, về mặt kết quả thông thường tương đương với `String.valueOf(value)`. Với object không null, có thể sử dụng `toString()` của object; phương thức đó có thể chứa logic hoặc tác dụng phụ. Kết quả và thứ tự đánh giá vẫn bị ràng buộc bởi ngữ nghĩa Java; không nên tự đoán rằng mọi object đã bị chuyển thành `String` ngay tại thời điểm biên dịch.

## 8. Hiệu năng: khi nào dùng `+`, khi nào dùng `StringBuilder`?

**Với một biểu thức nối chuỗi rõ ràng**, cách viết:

```java
String line = "user=" + user + ", count=" + count;
```

thường là lựa chọn sáng sủa. Trên Java hiện đại, `javac`/JVM có khả năng xây dựng và tối ưu toàn bộ phép nối, nên **không cần tự thay mọi dấu `+` bằng `StringBuilder`** vì tin rằng nó chắc chắn nhanh hơn. Sự tối ưu cụ thể tùy compiler, JVM, dữ liệu đầu vào và mức độ code chạy nóng.

**Với việc tích lũy chuỗi qua nhiều vòng lặp**, mỗi phép `+=` trên `String` có thể tạo một chuỗi trung gian mới, làm sao chép lặp đi lặp lại và có chi phí lớn khi dữ liệu tăng. Ví dụ cần xem xét:

```java
String output = "";
for (String item : items) {
    output += item;
}
```

Trong trường hợp tập hợp nhiều phần tử, một giải pháp rõ mục đích hơn thường là:

```java
StringBuilder builder = new StringBuilder();
for (String item : items) {
    builder.append(item);
}
String output = builder.toString();
```

Đây là **hai đoạn mã minh họa trong thân phương thức**, giả sử có biến `items` kiểu `Iterable<String>` hoặc một collection thích hợp. Không thể tuyên bố mọi vòng lặp `+=` đều chậm cùng một mức vì JVM có thể tối ưu trong một số trường hợp. Tuy nhiên, `StringBuilder` biểu đạt trực tiếp việc tích lũy nội dung và tránh phụ thuộc vào việc compiler/JIT có nhận ra cơ hội tối ưu toàn chuỗi qua nhiều lần lặp hay không.

Nếu có nhu cầu benchmark, hãy đo trong môi trường đại diện bằng công cụ microbenchmark như JMH; tránh lấy một lần gọi `System.nanoTime()` rồi suy luận toàn bộ hiệu năng. JIT warmup, dead-code elimination, escape analysis, GC và định dạng kết quả đều có thể ảnh hưởng.

**Không suy luận rằng `invokedynamic` luôn không cấp phát**. Các lớp runtime như `StringConcatFactory` cho phép JVM chọn chiến lược hiệu quả, nhưng chi tiết cấp phát/compact-string/JIT không phải cam kết cố định của cú pháp `+`.

## 9. Sai lầm thường gặp

1. **“Mọi phép cộng chuỗi đều gọi `StringBuilder`”:** nhận định này không còn đúng mặc định với `javac` Java 9+. Hãy kiểm tra bytecode khi cần.
2. **“Mọi dấu `+` đều thành `invokedynamic`”:** biểu thức hằng có thể được gộp sẵn; toán tử `+` số học là phép cộng số; compiler có thể dùng cơ chế khác.
3. **“`invokedynamic` nghĩa là gọi reflection mỗi lần”:** đây là lệnh bytecode có liên kết `CallSite`, không phải dò method theo tên trong mã nguồn mỗi lần nối.
4. **“`StringConcatFactory` làm `String` mutable”:** chuỗi kết quả vẫn có ngữ nghĩa `String` bất biến.
5. **“Thay `+` bằng `StringBuilder` chắc chắn nhanh hơn”:** phụ thuộc ngữ cảnh, compiler, JVM và workload; một biểu thức nối đơn giản thường nên ưu tiên dễ đọc.
6. **“`StringBuilder` không còn cần thiết”:** nó vẫn phù hợp cho xây dựng chuỗi gia tăng, đặc biệt trong vòng lặp.
7. **“Bytecode `invokedynamic` chứng minh runtime không cấp phát”:** bytecode và mã máy tối ưu là hai tầng khác nhau.
8. **“Có thể đảo thứ tự tính các toán hạng để tối ưu”:** Java yêu cầu giữ đúng thứ tự đánh giá, hiệu ứng phụ và ngoại lệ.
9. **“`null` trong `+` giống gọi `String.concat(null)`”:** phép nối có string conversion còn `concat` nhận tham số `null` có thể ném exception.
10. **“Đọc một output `javap` là đủ để khẳng định hành vi mọi JDK”:** output chịu ảnh hưởng version compiler, release target và hình dạng biểu thức. Hãy nêu rõ môi trường kiểm tra.

## 10. Quy trình tự kiểm tra một phép nối chuỗi

1. Xác định ý nghĩa biểu thức Java: đây là cộng số hay nối chuỗi, có `null`, phương thức có tác dụng phụ hay các phần hằng nào?
2. Biên dịch với release target bạn thực sự quan tâm, ví dụ `javac --release 17`.
3. Dùng `javap -c -v` để tìm `invokedynamic`, entry `BootstrapMethods`, bootstrap handle và recipe. Nếu thấy `ldc` với chuỗi đã gộp, đó có thể là constant folding.
4. Thực thi chương trình và kiểm tra **nội dung kết quả, thứ tự hiệu ứng phụ và cách xử lý `null`**; đừng chỉ nhìn lệnh bytecode.
5. Nếu mục tiêu là tối ưu hiệu năng, đánh giá công việc thực tế và benchmark nghiêm túc trước khi thay cấu trúc mã.

**Ghi nhớ:** `+` là cú pháp nối chuỗi ở cấp ngôn ngữ. Từ Java 9, `javac` thường chuyển phép nối động thành `invokedynamic`; JVM dùng `StringConcatFactory` làm bootstrap để liên kết một lời gọi có thể tối ưu. Cơ chế nội bộ thay đổi nhưng **ngữ nghĩa chuỗi bất biến, thứ tự đánh giá và kết quả phép nối phải được giữ nguyên**.
