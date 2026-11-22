# Kiểm tra xóa kiểu và phương thức bridge bằng javap

## 1. Mục tiêu của bài thực hành

Generics giúp compiler kiểm tra kiểu trong mã nguồn, nhưng cách biểu diễn phương thức trong class file sau biên dịch có thể khác hình thức `T`, `Box<String>` mà ta viết.

Bài thực hành dùng `javap` để trả lời bằng bằng chứng:

1. `T` không có cận tường minh được biểu diễn thành kiểu nào trong descriptor?
2. Lời gọi qua `Box<String>` tiếp tục gọi đúng phương thức ghi đè của lớp con như thế nào?
3. Compiler đặt các lệnh ép kiểu `checkcast` ở đâu?
4. Phương thức bridge được nhận diện bằng cờ nào?
5. Thông tin generic còn lại trong thuộc tính `Signature` khác descriptor ra sao?

Xóa kiểu (type erasure) là cơ chế của Java hiện đại, không chỉ là kiến thức lịch sử của Java 5. Quy tắc nền tảng nằm ở [JLS 4.6, Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6).

## 2. Chuẩn bị chương trình quan sát được cả đa hình lẫn lỗi kiểu

Lưu thành `ErasureBridgeLab.java`:

```java
public class ErasureBridgeLab {
    static class Box<T> {
        private T value;

        public void set(T value) {
            this.value = value;
        }

        public T get() {
            return value;
        }
    }

    static final class TextBox extends Box<String> {
        @Override
        public void set(String value) {
            super.set(value.trim());
        }

        @Override
        public String get() {
            return super.get();
        }
    }

    public static void main(String[] args) {
        Box<String> typed = new TextBox();
        typed.set("  Java  ");
        System.out.println(typed.get());

        Box raw = typed; // Co y dung raw type de quan sat loi.
        try {
            raw.set(42); // Co y tao unchecked invocation.
        } catch (ClassCastException ex) {
            System.out.println("rejected=" + ex.getClass().getSimpleName());
        }

        System.out.println("retained=" + typed.get());
    }
}
```

Các thành phần:

- `Box<T>` lưu một giá trị kiểu `T` theo kiểm tra tĩnh của mã nguồn.
- `TextBox extends Box<String>` chuyên biệt hóa hợp đồng kế thừa cho `String`.
- `TextBox.set(String)` ghi đè thao tác đặt giá trị và cắt khoảng trắng ở hai đầu.
- `TextBox.get()` ghi đè với kiểu trả về `String`.
- Biến `typed` có kiểu tĩnh `Box<String>`, nhưng đối tượng thật là `TextBox`.
- Đoạn raw type được đưa vào cố ý để thấy chỗ kiểm tra kiểu lúc chạy. Nó không phải mẫu API nên dùng trong ứng dụng.

Biên dịch với JDK 17+:

```shell
javac --release 17 -Xlint:rawtypes,unchecked -d out ErasureBridgeLab.java
java -cp out ErasureBridgeLab
```

Lệnh biên dịch dự kiến có hai nhóm cảnh báo:

```text
[rawtypes] found raw type: Box
[unchecked] unchecked call to set(T) as a member of the raw type Box
```

Đây là các phần cốt lõi của cảnh báo; đường dẫn, dòng và phần giải thích đầy đủ có thể khác theo compiler. Không tắt cảnh báo trong bài, vì chính chúng đánh dấu chỗ làm suy yếu kiểm tra generic.

Stdout của chương trình:

```text
Java
rejected=ClassCastException
retained=Java
```

Kết quả đầu tiên chứng minh lời gọi qua biến kiểu cha vẫn đi qua hành vi cắt khoảng trắng của lớp con. Kết quả cuối cho thấy lần gọi sai kiểu bị chặn trước khi thay giá trị đã lưu.

## 3. Dùng đúng class file và đúng tùy chọn javap

Các lớp lồng tạo ra những class file riêng:

```text
out/ErasureBridgeLab.class
out/ErasureBridgeLab$Box.class
out/ErasureBridgeLab$TextBox.class
```

Chạy:

```shell
javap -classpath out -p -s 'ErasureBridgeLab$Box'
javap -classpath out -p -c -s 'ErasureBridgeLab$TextBox'
javap -classpath out -p -v 'ErasureBridgeLab$TextBox'
javap -classpath out -p -c ErasureBridgeLab
```

Ý nghĩa:

| Tùy chọn | Dùng trong bài để |
| --- | --- |
| `-classpath out` | Chọn class file vừa biên dịch |
| `-p` | Hiển thị mọi thành viên, gồm trường private |
| `-s` | Hiển thị descriptor kiểu nội bộ |
| `-c` | Hiển thị lệnh bytecode |
| `-v` | Hiển thị chi tiết như flags và thuộc tính Signature |

Xem [tài liệu javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).

Dấu nháy đơn trong các lệnh trên bảo vệ ký tự `$` trên PowerShell và các shell tương tự. Nếu không bảo vệ, shell có thể diễn giải nó như biến và kiểm tra nhầm lớp.

`javap` phân tích class file, không phải tệp nguồn. Sau mỗi lần sửa, cần biên dịch lại và chắc chắn classpath trỏ vào output đúng. Không dựa vào một class file cũ trong thư mục khác.

## 4. Quan sát xóa kiểu ở Box

Trong kết quả `javap -p -s`, tìm:

```text
private T value;
  descriptor: Ljava/lang/Object;

public void set(T);
  descriptor: (Ljava/lang/Object;)V

public T get();
  descriptor: ()Ljava/lang/Object;
```

Vì `T` trong ví dụ không có cận tường minh, cận trên là `Object`. Sau xóa kiểu:

| Mã nguồn | Descriptor liên quan |
| --- | --- |
| Trường `T value` | `Ljava/lang/Object;` |
| `void set(T)` | `(Ljava/lang/Object;)V` |
| `T get()` | `()Ljava/lang/Object;` |

Cách đọc descriptor:

- `L...;` biểu diễn một kiểu tham chiếu theo tên nội bộ.
- Phần trong `(...)` là tham số.
- Phần sau `)` là kiểu trả về.
- `V` là `void`.
- `()` cho biết không có tham số tường minh.

Không rút ra quy tắc “mọi biến kiểu luôn thành Object”. Với cận như `T extends Number`, kiểu xóa của `T` là cận trái tương ứng, ở trường hợp đó là `Number`. Với kiểu generic có tham số như `List<String>`, kiểu xóa là kiểu thô `List`, không phải `Object`.

Ký hiệu `T` vẫn được javap hiển thị ở dòng giống khai báo nguồn vì nó còn đọc metadata generic; descriptor mới là phần cần nhìn để kiểm tra biểu diễn đã xóa kiểu.

## 5. Vấn đề cần bridge giải quyết

Ở mã nguồn, `TextBox.set(String)` ghi đè hợp đồng `set(T)` khi xét lớp cha là `Box<String>`.

Nhưng ở class file:

```text
Box.set       : (Object) -> void
TextBox.set   : (String) -> void
```

Để lời gọi theo descriptor đã xóa kiểu tiếp tục đến hành vi của lớp con, compiler sinh một phương thức thích nghi: **bridge method**.

Không phải bridge làm mất đa hình. Bridge chính là phần giúp giữ hành vi ghi đè trong cách biểu diễn bytecode sau xóa kiểu. Quy tắc liên quan tới ghi đè và erasure được thảo luận trong [JLS 8.4.8.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3).

Trong `TextBox`, javap cho thấy cả bốn phương thức sau, dù mã nguồn chỉ viết hai:

```text
public void set(java.lang.String);
public java.lang.String get();
public java.lang.Object get();
public void set(java.lang.Object);
```

Hai phương thức dạng `Object` trong lớp con là bridge do compiler tạo ở ví dụ này. Chúng là phương thức thật trong class file, không chỉ là tên hiển thị để javap giải thích.

Không cần và không nên tự chép các bridge tương đương trở lại lớp nguồn generic. Compiler chịu trách nhiệm sinh phần thích nghi theo quy tắc ngôn ngữ.

## 6. Đọc bridge setter: ép kiểu rồi chuyển tiếp

Phần bytecode của bridge setter trong lần biên dịch dùng cho bài:

```text
public void set(java.lang.Object);
  descriptor: (Ljava/lang/Object;)V
  Code:
       0: aload_0
       1: aload_1
       2: checkcast     #8                  // class java/lang/String
       5: invokevirtual #25                 // Method set:(Ljava/lang/String;)V
       8: return
```

Diễn giải:

1. `aload_0`: lấy tham chiếu `this`.
2. `aload_1`: lấy đối số có kiểu biểu diễn `Object`.
3. `checkcast String`: kiểm tra đối số có thể dùng như `String`.
4. `invokevirtual set(String)`: chuyển tới phương thức chuyên biệt do ta viết.
5. Kết thúc thao tác.

Luồng lời gọi khi dùng typed reference:

```text
typed.set("  Java  ")
    ↓ lời gọi theo descriptor Box.set(Object)
Đối tượng thật là TextBox
    ↓ dispatch đến bridge TextBox.set(Object)
checkcast String thành công
    ↓
TextBox.set(String)
    ↓
trim rồi lưu vào phần Box
```

Luồng lời gọi raw sai kiểu:

```text
raw.set(42)
    ↓ boxing 42 thành Integer
lời gọi theo set(Object)
    ↓ bridge của TextBox
checkcast Integer thành String thất bại
    ↓ ClassCastException
TextBox.set(String) chưa được thực hiện
```

Đây là lý do `retained=Java`: giá trị `Integer` chưa được đưa tới thao tác lưu của ví dụ này. Không suy ra rằng mọi raw write đều bị chặn ở setter; điều đó phụ thuộc phương thức và lớp thực tế. Một đối tượng `Box` thông thường chỉ có setter đã xóa kiểu có thể nhận `Object`, còn lỗi được phát hiện ở điểm đọc/ép kiểu về sau.

## 7. Đọc bridge getter và những lệnh checkcast khác nhau

Getter chuyên biệt do ta viết được biên dịch thành:

```text
public java.lang.String get();
  descriptor: ()Ljava/lang/String;
  Code:
       0: aload_0
       1: invokespecial #17                 // Method ErasureBridgeLab$Box.get:()Ljava/lang/Object;
       4: checkcast     #8                  // class java/lang/String
       7: areturn
```

`super.get()` có descriptor trả `Object`, nên phần triển khai `String get()` cần ép kết quả về `String`.

Bridge getter:

```text
public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
  Code:
       0: aload_0
       1: invokevirtual #21                 // Method get:()Ljava/lang/String;
       4: areturn
```

Bridge này gọi getter trả `String` rồi trả kết quả theo descriptor `Object`. Nó không cần một `checkcast String` riêng như bridge setter.

Ở nơi gọi qua `Box<String>`, javap của lớp ngoài còn cho thấy:

```text
18: invokevirtual #24                 // Method ErasureBridgeLab$Box.get:()Ljava/lang/Object;
21: checkcast     #28                 // class java/lang/String
24: invokevirtual #30                 // Method java/io/PrintStream.println:(Ljava/lang/String;)V
```

Compiler biết biểu thức `typed.get()` có kiểu tĩnh `String`, nhưng lời gọi class-file theo `Box.get()` trả `Object`, nên chèn cast ở nơi gọi.

Phân biệt ba chỗ:

| Vị trí | Vì sao có hoặc không có cast |
| --- | --- |
| Bridge setter `set(Object)` | Phải thu hẹp đối số trước khi gọi `set(String)` |
| Getter chuyên biệt `String get()` | Phải thu hẹp kết quả `super.get()` trả Object |
| Caller dùng `Box<String>` | Phải lấy lại kiểu tĩnh String từ descriptor trả Object |
| Bridge getter `Object get()` | Có thể trả String dưới dạng Object, không cần thu hẹp |

Chỉ thấy `checkcast` không đủ kết luận đó là bridge. Hãy xem phương thức chứa nó, descriptor và flags.

Số thứ tự constant pool như `#8`, `#25` và offset có thể đổi khi sửa mã hoặc đổi compiler. Hãy đối chiếu tên kiểu/phương thức và thứ tự thao tác, không ghi nhớ các số đó như hợp đồng Java.

## 8. Xác nhận bằng ACC_BRIDGE và ACC_SYNTHETIC

Trong output `javap -p -v`, hai phương thức dạng Object của `TextBox` có:

```text
flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

- `ACC_PUBLIC`: phương thức có quyền truy cập public.
- `ACC_BRIDGE`: đánh dấu bridge do compiler sinh.
- `ACC_SYNTHETIC`: phương thức không được khai báo trực tiếp như một phương thức thông thường trong nguồn.

Các cờ phương thức được quy định trong [JVMS, Methods](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.6).

Không coi mọi phương thức synthetic là bridge. Compiler có thể tạo thành phần synthetic cho những mục đích khác. Khi viết công cụ reflection, Java có `Method.isBridge()` và `Method.isSynthetic()`; cần dùng đúng ý nghĩa thay vì chỉ đếm số phương thức cùng tên.

Bridge cũng có thể liên quan tới kiểu trả về hiệp biến ngoài tình huống generic. Vì thế, thấy bridge không tự chứng minh class có một biến kiểu `T`.

### Vì sao có hai get() chỉ khác kiểu trả về trong class file?

Java nguồn không cho phép tự overload hai phương thức chỉ bằng kiểu trả về. Nhưng descriptor JVM chứa cả kiểu trả về, nên `()Ljava/lang/String;` và `()Ljava/lang/Object;` là hai descriptor khác nhau.

Đừng lấy danh sách javap rồi xem đó như một tệp nguồn Java có thể chép nguyên để biên dịch. Nó đang mô tả các thành phần của class file, gồm phần compiler sinh thêm.

## 9. Signature còn thông tin generic, descriptor vẫn dùng kiểu đã xóa

Chạy thêm:

```shell
javap -classpath out -p -v 'ErasureBridgeLab$Box'
```

Các thuộc tính đáng chú ý có nội dung:

```text
Field value:
  descriptor: Ljava/lang/Object;
  Signature: TT;

Method set:
  descriptor: (Ljava/lang/Object;)V
  Signature: (TT;)V

Method get:
  descriptor: ()Ljava/lang/Object;
  Signature: ()TT;
```

Đây là bảng trích ý nghĩa metadata; javap thực tế kèm số constant pool và nhiều phần khác. Ở `TextBox`, generic superclass còn được mô tả bằng:

```text
LErasureBridgeLab$Box<Ljava/lang/String;>;
```

Descriptor phục vụ biểu diễn kiểu khi thực thi; `Signature` lưu thông tin generic cho compiler/công cụ/reflection. Thuộc tính này được mô tả trong [JVMS, Signature Attribute](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9).

Do đó, hai phát biểu sau cần sửa:

- “Xóa kiểu là mọi dấu vết generic biến mất khỏi class file”: không đúng, vì metadata có thể còn.
- “Có Signature ghi Box<String> nên JVM tạo một bản Box riêng để chỉ lưu String”: không đúng; metadata không biến descriptor `Object` thành một lớp chuyên biệt theo từng đối số kiểu.

Bridge và cast bảo toàn hợp đồng nguồn trong mô hình đã xóa kiểu; chúng không tạo đầy đủ khả năng kiểm tra runtime cho mọi cấu trúc generic lồng nhau.

## 10. Thí nghiệm mở rộng và tiêu chí hoàn thành

### Thí nghiệm 1: xóa getter ghi đè

Bỏ `TextBox.get()`, biên dịch lại rồi xem class con. Dự kiến không còn bridge getter do phần ghi đè đó tạo ra; setter bridge vẫn cần cho `set(String)`.

Kiểm tra cả hành vi và bytecode; không chỉ nhìn số phương thức trong nguồn.

### Thí nghiệm 2: bỏ setter ghi đè

Bỏ `TextBox.set(String)`, biên dịch lại. Lời gọi raw lúc này có thể đi tới setter Object của lớp cha mà không gặp bridge setter của lớp con. Điểm phát hiện sai kiểu có thể chuyển sang lúc đọc/ép kiểu.

Dự đoán vị trí lỗi trước khi chạy. Đoạn `try/catch` hiện tại chỉ bao quanh `raw.set(42)`, nên không mặc định nó sẽ bắt được lỗi xảy ra ở lần đọc cuối.

### Thí nghiệm 3: tránh raw type

Đổi đoạn gọi sai thành:

```java
typed.set(42);
```

Đoạn này cố ý không biên dịch: compiler biết `typed` là `Box<String>`, nên không chấp nhận `int` thay `String`. Mục tiêu là thấy lỗi được phát hiện sớm khi giữ đầy đủ kiểm tra kiểu; không tìm cách tắt compiler để vượt qua lỗi.

Tiêu chí tự kiểm tra:

- Chỉ ra descriptor của trường, setter và getter trong Box.
- Tìm đúng hai bridge của TextBox ở bản gốc và chứng minh bằng flags.
- Giải thích cast nào làm raw.set(42) thất bại trong bản gốc.
- Phân biệt getter chuyên biệt, bridge getter và cast ở nơi gọi.
- Giải thích vì sao Signature vẫn có T/String dù descriptor đã xóa kiểu.
- Không nhầm output javap với source code hay hợp đồng về số constant pool.

Khi có các bằng chứng đó, ta không chỉ nhớ định nghĩa erasure/bridge mà còn kiểm tra được đường đi của một lời gọi đa hình trong class file thực tế.
