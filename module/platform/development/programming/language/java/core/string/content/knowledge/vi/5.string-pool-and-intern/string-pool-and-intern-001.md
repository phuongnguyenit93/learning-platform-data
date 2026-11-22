# String pool và việc dùng chung literal trong Java

## 1. String pool là gì?

**String pool** (hay *string intern pool*) là cơ chế Java dùng để quản lý các chuỗi đã được *intern*: mỗi nội dung chuỗi có một tham chiếu chuẩn (*canonical reference*) trong pool tại một thời điểm. Khi mã Java sử dụng literal như `"Java"`, JVM dùng tham chiếu của chuỗi đã được intern tương ứng; nhiều lần xuất hiện cùng literal có thể dùng chung một đối tượng `String`.

```java
String first = "Java";
String second = "Java";

System.out.println(first == second);      // true
System.out.println(first.equals(second)); // true
```

Hai phép so sánh đều trả về `true`, nhưng **vì hai lý do khác nhau**:

- `first == second` đúng vì hai biến tham chiếu **cùng đối tượng** `String` đã được intern.
- `first.equals(second)` đúng vì hai chuỗi có **cùng nội dung**.

Bản thân `String` là kiểu **bất biến** (*immutable*): sau khi đối tượng được tạo, các ký tự của đối tượng không thay đổi. Nhờ đó, các nơi giữ chung tham chiếu đến một literal không thể sửa nội dung và làm ảnh hưởng nhau. Đây là một cơ sở quan trọng cho việc chia sẻ chuỗi an toàn qua pool.

**Giới hạn cần nhớ:** Pool không có nghĩa mọi đối tượng `String` có cùng nội dung đều là cùng một đối tượng. Java vẫn cho phép tạo các đối tượng `String` khác nhau nhưng `equals()` trả về `true`.

## 2. Literal được dùng chung như thế nào?

**String literal** là chuỗi viết trực tiếp trong mã nguồn, ví dụ `""`, `"hello"`, `"Xin chào"`. Java Language Specification quy định literal chuỗi (và kết quả biểu thức hằng kiểu chuỗi) được intern, qua đó cùng nội dung sẽ có tham chiếu chuẩn.

```java
String a = "hello";
String b = "hello";
String c = "world";

System.out.println(a == b); // true
System.out.println(a == c); // false
```

Dòng thứ nhất so sánh hai literal giống nhau nên `true`. Dòng thứ hai là hai nội dung khác nhau nên không thể là cùng chuỗi, trả về `false`.

Có thể hình dung:

```text
                  String pool (mô hình khái niệm)

a --------------------+
                      +----> String "hello"
b --------------------+

c --------------------------> String "world"
```

Sơ đồ chỉ minh họa việc **dùng chung tham chiếu**, không khẳng định bố trí ô nhớ, địa chỉ hay thuật toán thực thi của một JVM cụ thể.

### Literal giống nhau có thể nằm ở nhiều nơi trong chương trình

Nếu các lớp, phương thức hay phần khác nhau của một chương trình chạy trong cùng JVM sử dụng các chuỗi literal giống nội dung, các literal đó được intern và có thể cùng tham chiếu đến chuỗi chuẩn. Cơ chế này không đòi hỏi lập trình viên tự gọi `intern()` trên từng literal.

**Không suy ra số lượng đối tượng chỉ bằng cách đếm dòng mã:** Một literal xuất hiện nhiều lần không hàm ý có chừng ấy đối tượng, và thời điểm đối tượng được tạo/lấy từ pool phụ thuộc quá trình tải, liên kết, thực thi lớp cũng như chi tiết triển khai.

## 3. Kiểm chứng việc chia sẻ literal qua hai lớp

Ví dụ trên chỉ dùng một phương thức; hãy thử viết literal cùng nội dung ở **hai lớp khác nhau** trong tệp `LiteralAcrossClasses.java`:

~~~java
class LiteralProvider {
    static String getLabel() {
        return "java-pool";
    }
}

public class LiteralAcrossClasses {
    public static void main(String[] args) {
        String local = "java-pool";
        String anotherClass = LiteralProvider.getLabel();
        String constructed = new String("java-pool");

        System.out.println(local == anotherClass);
        System.out.println(local == constructed);
        System.out.println(local.equals(constructed));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LiteralAcrossClasses.java
java LiteralAcrossClasses
~~~

~~~text
true
false
true
~~~

Hai literal giống nhau dùng chung tham chiếu dù nằm ở hai lớp. `constructed` là đối tượng riêng do `new` tạo nhưng có nội dung bằng nhau. Việc các class file có bảng constant pool riêng **không** đồng nghĩa mỗi lớp có một string pool riêng: metadata của class file và đối tượng interned lúc chạy là hai tầng khác nhau.

## 4. Liên hệ với tính bất biến và cấu trúc dữ liệu

Pool hoạt động an toàn vì `String` bất biến. Ví dụ:

```java
String one = "color";
String two = "color";

one = one.replace('c', 'C');

System.out.println(one); // Color
System.out.println(two); // color
```

`replace()` trả về một chuỗi có nội dung khác; đối tượng `"color"` gốc không bị sửa. Việc `one` đổi tham chiếu không ảnh hưởng `two`.

Tương tự, `String` thích hợp làm khóa cho `HashMap` vì nội dung dùng bởi `equals()` và `hashCode()` không biến đổi sau khi chèn. Việc được intern **không phải điều kiện** để `HashMap` nhận diện hai khóa chuỗi bằng nhau:

```java
java.util.Map<String, Integer> counts = new java.util.HashMap<>();
counts.put("Java", 5);

String key = new String("Java");
System.out.println(counts.get(key)); // 5
```

`HashMap` dùng `hashCode()` và `equals()` theo hợp đồng của khóa, không bắt buộc hai khóa phải trỏ cùng đối tượng.

Pool và tính bất biến cũng không tự làm mọi thao tác với biến `String` chia sẻ giữa các thread trở nên an toàn về thứ tự thực thi/khả năng quan sát. Chia sẻ **nội dung đối tượng bất biến** và cập nhật **biến tham chiếu chung** là hai việc khác nhau; trường hợp thứ hai vẫn phải tuân theo Java Memory Model và chiến lược đồng bộ phù hợp.

## 5. Giới hạn của điều quan sát được

- Pool quản lý **chuỗi đã intern**, không phải mọi `String` được tạo từ file, request, JSON hay phép nối runtime.
- `"Ja" + "va"` là biểu thức hằng có kết quả `"Java"` nên được intern; phép nối với biến không phải constant variable là một tình huống khác. Bài về biểu thức hằng và nối runtime sẽ phân tích ranh giới này.
- `intern()` lấy **tham chiếu chuẩn** cho nội dung; nó không chỉnh sửa biến gọi phương thức và không chuyển đổi chữ hoa/thường, khoảng trắng hay Unicode.
- Không suy diễn vị trí bộ nhớ hoặc số lần cấp phát từ số literal trong source. Phân giải class, thời điểm sử dụng và tối ưu JVM có thể khác nhau.
- Trong logic kiểm tra nội dung, dùng `equals()`; một kết quả `== true` trên literal chỉ chứng minh hai tham chiếu đang cùng đối tượng.

## 6. Tự kiểm tra

Hãy dự đoán bốn kết quả sau:

```java
String x = "code";
String y = "co" + "de";
String part = "co";
String z = part + "de";
String t = new String("code");

System.out.println(x == y);
System.out.println(x == z);
System.out.println(x == t);
System.out.println(z.intern() == x);
```

Kết quả:

```text
true
false
false
true
```

Giải thích: `y` là kết quả biểu thức hằng được intern; `z` là phép nối với biến thực hiện lúc chạy; `t` là đối tượng tạo riêng bằng `new`; `z.intern()` trả về tham chiếu chuẩn của literal `"code"`.

**Ghi nhớ:** *Cùng nội dung* (`equals`) và *cùng đối tượng* (`==`) là hai khái niệm khác nhau. String pool giúp literal và chuỗi đã intern chia sẻ tham chiếu chuẩn; nó không phải quy tắc so sánh nội dung cho chương trình Java.