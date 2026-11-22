# Kiểm tra bytecode bằng javap: abstract flag, interface flag và bridge method

Khi đọc mã nguồn Java, ta thấy lớp trừu tượng, interface và các phương thức generic ở mức ngôn ngữ. Sau khi biên dịch, JVM làm việc với các tệp class, descriptor và cờ truy cập. Công cụ **javap** giúp kiểm tra những gì trình biên dịch thực sự tạo ra, đặc biệt là ba dấu hiệu **ACC_ABSTRACT**, **ACC_INTERFACE** và **ACC_BRIDGE**.

Bài này dùng một ví dụ nhỏ có thể biên dịch bằng Java 17+, rồi đọc phần bytecode liên quan thay vì suy luận chỉ từ mã nguồn.

## 1. javap dùng để làm gì?

**javap** là công cụ đi kèm JDK để phân tích tệp class. Một số tùy chọn hữu ích:

| Tùy chọn | Tác dụng |
|---|---|
| **-p** | Hiển thị cả thành viên private, ngoài các thành viên thông thường |
| **-v** | Hiển thị thông tin chi tiết: phiên bản class file, flags, constant pool và attributes |
| **-s** | Hiển thị descriptor nội bộ của lớp và phương thức |
| **-c** | Hiển thị các lệnh bytecode trong phần Code |
| **-classpath** hoặc **-cp** | Chỉ định nơi tìm các tệp class |

Ví dụ, **javap -v -p StringMapper** cho biết các flags của lớp và phương thức, còn **javap -c -p StringMapper** giúp nhìn các lệnh của phương thức cầu nối do compiler sinh ra. Có thể kết hợp các tùy chọn, chẳng hạn **javap -v -p -c StringMapper**.

Hãy chạy javap trên tệp **.class** đã biên dịch. Nếu vừa sửa mã nguồn nhưng chưa biên dịch lại, kết quả javap vẫn phản ánh phiên bản class cũ.

## 2. Các flag cần phân biệt

Flags là các bit trong cấu trúc class file. javap thường trình bày chúng dưới dạng giá trị hex và danh sách tên dễ đọc.

| Flag | Giá trị | Ngữ cảnh | Ý nghĩa |
|---|---:|---|---|
| **ACC_ABSTRACT** | **0x0400** | Lớp hoặc phương thức | Lớp không thể khởi tạo trực tiếp; với phương thức, phần thân được để trống và lớp cụ thể phải cung cấp cách triển khai khi cần |
| **ACC_INTERFACE** | **0x0200** | Lớp file biểu diễn interface | Đánh dấu kiểu đó là interface |
| **ACC_BRIDGE** | **0x0040** | Phương thức | Đánh dấu phương thức cầu nối do compiler sinh ra để bảo toàn cách dispatch, thường gặp cùng generic và type erasure |
| **ACC_SYNTHETIC** | **0x1000** | Thành viên | Đánh dấu thành viên được compiler sinh ra, không tương ứng trực tiếp với khai báo tường minh trong mã nguồn |
| **ACC_PUBLIC** | **0x0001** | Lớp hoặc thành viên | Thành viên có thể truy cập công khai; với lớp top-level, chỉ xuất hiện nếu lớp được khai báo public |
| **ACC_SUPER** | **0x0020** | Lớp thông thường | Flag class file thường thấy ở lớp Java; không có nghĩa là lớp abstract hoặc có lớp cha do ta tự khai báo |

Một điểm quan trọng: cách diễn giải flag phụ thuộc ngữ cảnh. Không nên đọc một giá trị bit tách khỏi việc nó đang thuộc flags của lớp, phương thức hay trường.

**ACC_ABSTRACT** và **ACC_INTERFACE** không đồng nghĩa. Một interface có flag lớp **ACC_INTERFACE** và cũng có **ACC_ABSTRACT** ở cấp class file. Một phương thức abstract có **ACC_ABSTRACT** ở flags của chính phương thức. Một lớp abstract có **ACC_ABSTRACT** ở flags của lớp, nhưng không có **ACC_INTERFACE**.

Interface vẫn mang flag lớp abstract ngay cả khi có phương thức **default**, **static** hoặc **private** có phần thân. Các phương thức interface có phần thân không nhất thiết mang **ACC_ABSTRACT**.

## 3. Ví dụ Java 17+ có thể chạy

Tạo tệp tên **BytecodeFlagsDemo.java** với nội dung sau. Interface và lớp abstract trong ví dụ được đặt cùng tệp để việc thử nghiệm đơn giản hơn.

~~~java
interface Mapper<T> {
    T map(T value);
}

abstract class Base {
    public abstract Number value();
}

final class StringMapper implements Mapper<String> {
    @Override
    public String map(String value) {
        return value.trim();
    }
}

public class BytecodeFlagsDemo {
    public static void main(String[] args) {
        Mapper<String> mapper = new StringMapper();
        System.out.println(mapper.map("  Java  "));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac --release 17 BytecodeFlagsDemo.java
java BytecodeFlagsDemo
~~~

Stdout:

~~~text
Java
~~~

Tùy chọn **--release 17** yêu cầu compiler tạo bytecode tương thích Java 17 và giới hạn API theo phiên bản đó. Khi dùng compiler Java 17, class file có major version **61**.

Lệnh biên dịch sẽ tạo các tệp class, gồm **Mapper.class**, **Base.class**, **StringMapper.class** và **BytecodeFlagsDemo.class**. Mỗi tệp class mô tả một kiểu riêng; vì vậy cần kiểm tra đúng tên lớp khi chạy javap.

## 4. Kiểm tra abstract flag của lớp và phương thức

Chạy:

~~~bash
javap -v -p Base
~~~

Trong phần đầu output, hãy tìm flags của lớp. Phần liên quan sẽ có dạng:

~~~text
abstract class Base
  ...
  flags: (0x0420) ACC_SUPER, ACC_ABSTRACT
~~~

Lớp **Base** có **ACC_ABSTRACT**, vì được khai báo abstract. Flag **ACC_SUPER** là flag thông thường của lớp Java và không có nghĩa rằng Base là abstract.

Tiếp theo, tìm phương thức **value()**:

~~~text
public abstract java.lang.Number value();
  descriptor: ()Ljava/lang/Number;
  flags: (0x0401) ACC_PUBLIC, ACC_ABSTRACT
~~~

Phương thức không có phần thân Java, nên class file không chứa một phần Code thông thường cho phương thức này. Descriptor **()Ljava/lang/Number;** nghĩa là không có tham số và kiểu trả về là **java.lang.Number**.

Một lớp cụ thể kế thừa Base phải triển khai phương thức abstract còn thiếu, nếu không lớp đó cũng phải được khai báo abstract. Việc nhìn flag ở cấp lớp và flag ở cấp phương thức giúp xác định hai khái niệm riêng này.

## 5. Kiểm tra interface flag

Chạy:

~~~bash
javap -v -p Mapper
~~~

Phần đầu output sẽ thể hiện kiểu là interface và các flags cấp lớp:

~~~text
interface Mapper<T>
  ...
  flags: (0x0600) ACC_INTERFACE, ACC_ABSTRACT
~~~

Đây là dấu hiệu chính để nhận biết class file đang biểu diễn một interface. Giá trị **0x0600** là tổng của **ACC_INTERFACE (0x0200)** và **ACC_ABSTRACT (0x0400)**.

Phương thức generic trong interface có dạng:

~~~text
public abstract T map(T);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (0x0401) ACC_PUBLIC, ACC_ABSTRACT
  Signature: #... // (TT;)TT;
~~~

Dòng **descriptor** và dòng **Signature** trả lời hai câu hỏi khác nhau:

- **Descriptor** là kiểu dùng cho liên kết và gọi ở cấp JVM. Sau type erasure, tham số T và kết quả T của phương thức này đều trở thành **java.lang.Object**.
- **Signature** giữ lại thông tin generic để công cụ và compiler có thể biểu diễn kiểu nguồn **T**. Chỉ số constant pool trong output thật sẽ phụ thuộc quá trình biên dịch; dấu **#...** ở đây là phần lược bỏ minh họa, không phải văn bản literal của javap.

Đừng kết luận rằng interface không có phương thức thực thi chỉ vì class file có **ACC_ABSTRACT**. Flag này mô tả kiểu interface ở cấp lớp; từng phương thức vẫn có flags riêng. Phương thức abstract không có phần thân, còn phương thức default hoặc static có phần thân và không mang **ACC_ABSTRACT** ở cấp phương thức.

## 6. Vì sao compiler tạo bridge method?

Java generic chủ yếu được triển khai bằng **type erasure**. Trong ví dụ, khai báo nguồn là **Mapper&lt;T&gt;** với phương thức **T map(T value)**. Sau erasure, descriptor của phương thức trong interface là:

~~~text
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Nhưng lớp **StringMapper** triển khai phương thức chuyên biệt:

~~~java
public String map(String value)
~~~

Descriptor của phương thức này là:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

Hai descriptor khác nhau. Ở cấp JVM, phương thức nhận Object không giống phương thức nhận String. Để lời gọi theo hợp đồng đã bị xóa kiểu vẫn được dispatch đến phần triển khai chuyên biệt, compiler sinh một **bridge method** có descriptor đã xóa kiểu. Phương thức cầu nối kiểm tra và chuyển đối số rồi gọi phương thức thực sự trong StringMapper.

Bridge method không cần được viết trong mã nguồn. Nó là một thành viên bổ sung ở bytecode để giữ hành vi đa hình khi generic bị xóa kiểu. Cùng ý tưởng này cũng có thể xuất hiện với một số trường hợp override có kiểu trả về hiệp biến.

## 7. Dùng javap để tìm bridge method

Chạy:

~~~bash
javap -v -p StringMapper
~~~

Trong output, sẽ thấy phương thức nguồn:

~~~text
public java.lang.String map(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  flags: (0x0001) ACC_PUBLIC
~~~

Và một phương thức bổ sung có dạng:

~~~text
public java.lang.Object map(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

Ba flag trên có thể đọc như sau:

- **ACC_PUBLIC**: bridge có thể được gọi theo phạm vi truy cập công khai.
- **ACC_BRIDGE**: đây là phương thức cầu nối.
- **ACC_SYNTHETIC**: compiler đánh dấu phương thức này là thành viên được sinh ra.

Giá trị **0x1041** tương ứng **0x0001 + 0x0040 + 0x1000**. Hãy nhìn cả danh sách tên flag thay vì chỉ ghi nhớ con số.

Vì output chi tiết có thể dài, hãy tập trung vào tên phương thức, descriptor, flags và phần Code của phương thức nhận Object. Các số chỉ mục constant pool có thể khác giữa các bản biên dịch; điều cần đối chiếu là descriptor và hành vi.

## 8. Đọc phần Code của bridge

Có thể yêu cầu javap hiển thị bytecode:

~~~bash
javap -c -p StringMapper
~~~

Bridge method sẽ có các lệnh tương đương đoạn sau; chỉ số constant pool và phần chú thích có thể khác:

~~~text
public java.lang.Object map(java.lang.Object);
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #... // class java/lang/String
     5: invokevirtual #... // Method map:(Ljava/lang/String;)Ljava/lang/String;
     8: areturn
~~~

Đọc theo thứ tự:

1. **aload_0** đẩy đối tượng hiện tại lên operand stack.
2. **aload_1** đẩy tham số Object lên stack.
3. **checkcast java/lang/String** kiểm tra và chuyển kiểu tham số sang String. Nếu caller truyền một kiểu không phù hợp, lệnh này có thể ném **ClassCastException**.
4. **invokevirtual map(String)** gọi phần triển khai thực sự trong StringMapper.
5. **areturn** trả về tham chiếu kết quả. String là kiểu tham chiếu, vì vậy dùng lệnh trả về tham chiếu.

Bridge method không phải một bản sao chứa logic nghiệp vụ độc lập. Nó chuyển lời gọi theo descriptor đã xóa kiểu sang phương thức chuyên biệt. Đó là lý do phương thức bridge thường ngắn và có các lệnh cast cùng gọi phương thức khác.

## 9. Quy trình chẩn đoán bằng javap

Khi cần xác nhận compiler đã tạo đúng cấu trúc:

1. **Biên dịch lại** mã nguồn bằng JDK và tùy chọn phiên bản mong muốn.
2. **Kiểm tra đúng class** bằng javap. Nếu class nằm trong package hoặc thư mục build riêng, truyền đúng tên đầy đủ hoặc classpath.
3. **Dùng -v** để xem flags và attributes.
4. **Dùng -s** để đối chiếu descriptor, nhất là khi generic bị xóa kiểu.
5. **Dùng -c** để kiểm tra bridge thực hiện cast và gọi phương thức nào.
6. **So sánh phương thức nguồn và bridge**: tên có thể giống nhau, nhưng tham số hoặc kiểu trả về trong descriptor khác nhau.
7. **Xác nhận flag ở đúng cấp**: flag lớp không thay thế flag phương thức, và flag của bridge không phải flag của cả lớp.

Một lệnh hữu ích để kiểm tra nhanh descriptor và bytecode là:

~~~bash
javap -p -s -c StringMapper
~~~

Nếu cần xem flags chi tiết, dùng thêm **-v**. Để xem các thành viên không public, giữ **-p**; nếu thiếu tùy chọn này, một số thông tin có thể không xuất hiện như mong đợi.

## 10. Những nhầm lẫn thường gặp

- **Nhầm ACC_ABSTRACT với ACC_INTERFACE:** interface mang cả hai flag ở cấp lớp, còn một abstract class có ACC_ABSTRACT mà không có ACC_INTERFACE.
- **Chỉ nhìn tên phương thức:** hai phương thức cùng tên có thể khác descriptor. Hãy kiểm tra tham số, kiểu trả về và descriptor nội bộ.
- **Cho rằng phương thức bridge được viết trong source:** bridge thường do compiler tạo. Dùng javap hoặc Reflection API để nhận diện.
- **Cho rằng ACC_SYNTHETIC đồng nghĩa với ACC_BRIDGE:** synthetic là nhãn tổng quát cho thành viên do compiler sinh; bridge là một loại phương thức có mục đích cụ thể.
- **Đọc Signature như descriptor:** Signature có thể giữ kiểu generic, còn descriptor phản ánh kiểu sau erasure được dùng trong liên kết JVM.
- **Không biên dịch lại sau khi sửa source:** javap đọc tệp class trên đĩa, nên có thể hiển thị kết quả cũ.
- **So sánh số constant pool giữa các bản build:** các chỉ số như **#7** không phải định danh ổn định. Hãy so sánh tên phương thức, descriptor, flags và lệnh bytecode.
- **Cho rằng mọi interface method đều abstract:** phương thức default, static và private có phần thân; hãy xem flags của từng phương thức.
- **Bỏ qua ClassCastException trong bridge:** bridge có thể cast từ Object về kiểu chuyên biệt. Lời gọi thô (raw type) hoặc mã không an toàn với generic có thể truyền đối số sai kiểu.

## 11. Checklist đọc kết quả

- Lớp abstract có **ACC_ABSTRACT** ở flags cấp lớp.
- Interface có **ACC_INTERFACE** và **ACC_ABSTRACT** ở flags cấp lớp.
- Phương thức abstract có **ACC_ABSTRACT** ở flags của phương thức.
- Phương thức nguồn và bridge được so sánh bằng descriptor, không chỉ bằng tên.
- Bridge do compiler sinh thường có **ACC_BRIDGE** và **ACC_SYNTHETIC**.
- Phần Code của bridge cho thấy cách nó chuyển đối số và gọi phương thức chuyên biệt.
- Đã biên dịch lại và kiểm tra đúng tệp class.

Khi phân tích bytecode, hãy luôn xác định **flag thuộc về lớp hay phương thức**, rồi đối chiếu với **descriptor** và **Code**. Ba loại thông tin này kết hợp với nhau sẽ giải thích rõ vì sao một lớp abstract, một interface hoặc một phương thức cầu nối xuất hiện trong kết quả biên dịch.