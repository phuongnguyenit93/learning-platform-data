
# Method descriptor và khác biệt với chữ ký ở mức mã nguồn

Khi Java biên dịch một method, compiler chuyển khai báo ở mức mã nguồn thành một biểu diễn nhị phân mà JVM dùng để liên kết và gọi method. Biểu diễn này được gọi là **method descriptor**. Nó có cấu trúc và quy tắc riêng, khác với chữ ký method mà lập trình viên nhìn thấy trong Java source.

Sự khác biệt này rất quan trọng khi đánh giá binary compatibility. Hai method có thể trông gần như giống nhau ở mức mã nguồn nhưng có descriptor khác nhau; ngược lại, hai khai báo generic khác nhau có thể bị type erasure chuyển thành cùng một descriptor. Compiler còn có thể sinh bridge method để duy trì quan hệ override sau khi xóa generic hoặc khi dùng kiểu trả về hiệp biến.

Nếu chỉ so sánh tên method và danh sách tham số trong source, nhóm migration có thể bỏ sót thay đổi làm bytecode cũ không liên kết được với thư viện mới. Bài học này giải thích cấu trúc descriptor, đối chiếu nó với source-level signature, cách quan sát bằng công cụ và cách dùng thông tin đó để kiểm tra tương thích nhị phân.

## 1. Method signature ở mức mã nguồn là gì?

Trong Java, method signature được xác định bởi tên method, các type parameters của method (nếu có) và các kiểu tham số hình thức, theo quy tắc adaptation của Java Language Specification. Điểm cần nhớ là **return type không phải thành phần dùng để phân biệt overload ở mức source**.

Ví dụ:

~~~java
public class Converter {
    public String convert(int value) {
        return Integer.toString(value);
    }

    public String convert(long value) {
        return Long.toString(value);
    }
}
~~~

Hai method có cùng tên nhưng khác kiểu tham số nên có signature khác nhau. Compiler có thể chọn method phù hợp dựa trên kiểu đối số và quy tắc overload resolution.

Ngược lại, khai báo sau không hợp lệ trong Java:

~~~java
public class Converter {
    public String convert(int value) {
        return Integer.toString(value);
    }

    public long convert(int value) {
        return value;
    }
}
~~~

Hai method có cùng tên và cùng kiểu tham số. Chỉ thay return type không tạo ra một overload hợp lệ ở mức source.

Một source-level signature cũng không bao gồm các thông tin sau:

| Thông tin | Có dùng để phân biệt method signature ở mức source không? |
|---|---|
| Tên method | Có |
| Type parameters và kiểu tham số | Có, theo quy tắc signature của Java |
| Return type | Không |
| Tên tham số | Không |
| Mệnh đề throws | Không |
| Annotation | Không |
| Access modifier như public/private | Không |
| static hay instance | Không tạo ra overload khác nếu tên và tham số trùng |

Một số thông tin không thuộc signature vẫn có thể ảnh hưởng đến việc gọi, quyền truy cập, kiểm tra kiểu, hành vi hoặc cách compiler phát sinh bytecode. Chúng chỉ không phải thành phần phân biệt overload theo quy tắc source-level.

## 2. Method descriptor ở mức JVM là gì?

JVM không dùng cách mô tả method giống Java source. Trong class file, một method có tên và một **descriptor**. Descriptor mô tả chính xác các kiểu tham số và kiểu trả về sau khi chuyển sang dạng JVM.

Cấu trúc tổng quát:

~~~text
(parameter-descriptor...)return-descriptor
~~~

Dấu ngoặc tròn bao quanh danh sách tham số; phần sau dấu ngoặc đóng là kiểu trả về.

Ví dụ:

| Khai báo Java | Method descriptor |
|---|---|
| void run() | ()V |
| int add(int a, int b) | (II)I |
| String find(int id) | (I)Ljava/lang/String; |
| void send(String value) | (Ljava/lang/String;)V |
| long sum(int[] values) | ([I)J |
| Object lookup(String key, int index) | (Ljava/lang/String;I)Ljava/lang/Object; |

Descriptor không chứa tên method. Trong class file, tên method và descriptor là hai mục riêng. Khi JVM liên kết một lời gọi, symbolic reference xác định class/interface sở hữu, tên method và descriptor. Vì vậy, hai method khác tên có thể có cùng descriptor mà vẫn là hai method khác nhau.

### 2.1. Ký hiệu kiểu dữ liệu

Các kiểu primitive và void có ký hiệu cố định:

| Kiểu Java | Descriptor |
|---|---|
| byte | B |
| char | C |
| double | D |
| float | F |
| int | I |
| long | J |
| short | S |
| boolean | Z |
| void (chỉ kiểu trả về) | V |

Kiểu tham chiếu dùng dạng:

~~~text
Lbinary/name/of/Class;
~~~

Ví dụ:

| Kiểu Java | Descriptor |
|---|---|
| String | Ljava/lang/String; |
| java.util.List | Ljava/util/List; |
| com.example.User | Lcom/example/User; |

Tên package dùng dấu gạch chéo trong descriptor. Với inner class, tên nhị phân thường chứa ký tự đô la:

~~~text
Lcom/example/Outer$Inner;
~~~

Mảng dùng dấu ngoặc vuông ở đầu descriptor của kiểu phần tử:

| Kiểu Java | Descriptor |
|---|---|
| int[] | [I |
| long[][] | [[J |
| String[] | [Ljava/lang/String; |
| User[][] | [[Lcom/example/User; |

### 2.2. Tạo descriptor từng bước

Xét method:

~~~java
public String find(int id, boolean active) {
    return "user";
}
~~~

Chuyển từng tham số:

- int thành I.
- boolean thành Z.
- Kiểu trả về String thành Ljava/lang/String;.

Ghép theo cấu trúc method descriptor:

~~~text
(IZ)Ljava/lang/String;
~~~

Xét method khác:

~~~java
public void save(String name, long version, byte[] data) {
}
~~~

Các tham số lần lượt là String, long và byte[]; kiểu trả về void. Descriptor:

~~~text
(Ljava/lang/String;J[B)V
~~~

Việc chuyển đổi này không phụ thuộc tên tham số. Đổi tên name thành username không làm descriptor thay đổi.

## 3. Descriptor có bao gồm return type

Đây là khác biệt quan trọng nhất giữa method signature trong Java source và method descriptor của JVM.

Ví dụ hai khai báo giả định:

~~~java
String getValue(int id)
Object getValue(int id)
~~~

Ở mức source, hai method có cùng tên và cùng kiểu tham số nên không thể khai báo thành hai overload trong cùng một class Java thông thường.

Ở mức JVM, descriptor lần lượt là:

~~~text
(I)Ljava/lang/String;
(I)Ljava/lang/Object;
~~~

Descriptor khác nhau vì return type được đưa vào. JVM class file có thể biểu diễn các method có cùng tên và cùng tham số nhưng khác return descriptor, dù Java source không cho phép lập trình viên khai báo trực tiếp hai method như vậy.

Điều này có thể xuất hiện khi:

- Compiler sinh bridge method.
- Ngôn ngữ khác chạy trên JVM có quy tắc source khác Java.
- Bytecode được tạo hoặc biến đổi bằng ASM, Byte Buddy hoặc công cụ tương tự.

### 3.1. Thay return type có thể phá vỡ binary compatibility

Giả sử phiên bản thư viện 1 có:

~~~java
public class UserRepository {
    public User find(long id) {
        return null;
    }
}
~~~

Method descriptor:

~~~text
(J)Lcom/example/User;
~~~

Phiên bản thư viện 2 thay return type thành một kiểu khác:

~~~java
public class UserRepository {
    public Optional<User> find(long id) {
        return Optional.empty();
    }
}
~~~

Descriptor mới:

~~~text
(J)Ljava/util/Optional;
~~~

Một consumer đã biên dịch với phiên bản 1 chứa tham chiếu tới method có descriptor cũ. Khi chạy với phiên bản 2 mà không còn method đó, JVM có thể ném:

~~~text
java.lang.NoSuchMethodError
~~~

Ở source, tên method và kiểu tham số vẫn giống nhau. Nhưng binary reference đã thay đổi vì return type nằm trong descriptor.

Đây là lý do kiểm tra binary compatibility không thể chỉ so sánh tên method và tham số.

## 4. Generic và type erasure

Java generic được kiểm tra chủ yếu ở compile time. Khi biên dịch, compiler áp dụng **type erasure** để chuyển các kiểu tham số hóa thành kiểu JVM tương ứng.

Ví dụ:

~~~java
public interface Store<T> {
    T get();
    void put(T value);
}
~~~

Nếu T không có bound cụ thể, erasure của T là Object. Các descriptor tương ứng:

~~~text
get: ()Ljava/lang/Object;
put: (Ljava/lang/Object;)V
~~~

Trong khi source có T, descriptor JVM không chứa tên type variable T. Thông tin generic có thể được giữ riêng trong class file attribute có tên Signature để compiler, reflection và công cụ đọc metadata sử dụng.

Ví dụ method generic:

~~~java
public <T> T identity(T value) {
    return value;
}
~~~

Descriptor sau erasure:

~~~text
(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Generic Signature attribute có thể giữ thông tin rằng tham số và kết quả dùng cùng type variable T. Hai dạng metadata phục vụ hai mục tiêu khác nhau:

| Thành phần | Mục đích |
|---|---|
| Descriptor | Liên kết và gọi method ở mức JVM |
| Signature attribute | Giữ thông tin generic để công cụ và reflection có thể đọc |
| Source declaration | Thể hiện kiểu generic cho lập trình viên và compiler |

### 4.1. Bound làm thay đổi erasure

Nếu type variable có bound:

~~~java
public <T extends Number> T normalize(T value) {
    return value;
}
~~~

Erasure của T là Number, không phải Object. Descriptor:

~~~text
(Ljava/lang/Number;)Ljava/lang/Number;
~~~

Nếu thay bound từ Number thành Serializable, descriptor có thể đổi thành:

~~~text
(Ljava/io/Serializable;)Ljava/io/Serializable;
~~~

Ngay cả khi tên method và cấu trúc generic trông tương tự, thay bound có thể thay đổi descriptor và phá vỡ liên kết của bytecode cũ.

### 4.2. Thay đổi generic có thể không đổi descriptor

Giả sử phiên bản 1:

~~~java
public List<String> names() {
    return List.of();
}
~~~

Phiên bản 2:

~~~java
public List<CharSequence> names() {
    return List.of();
}
~~~

Cả hai đều có descriptor:

~~~text
()Ljava/util/List;
~~~

Vì generic type argument bị xóa khỏi descriptor. Do đó, thay đổi này có thể không làm JVM mất method ở bước linkage, nhưng vẫn có thể gây source incompatibility, thay đổi generic metadata, lỗi ở consumer khi biên dịch lại hoặc thay đổi hành vi.

Không nên kết luận rằng descriptor không đổi nghĩa là thay đổi hoàn toàn an toàn. Binary linkage là một phần của tương thích, không bao quát mọi hợp đồng source và behavioral.

## 5. Bridge method và synthetic method

Compiler Java có thể sinh method mà lập trình viên không khai báo trực tiếp. Hai cờ class file thường gặp:

- ACC_BRIDGE: method cầu nối do compiler tạo để duy trì quan hệ override sau type erasure hoặc kiểu trả về hiệp biến.
- ACC_SYNTHETIC: method hoặc thành phần được compiler tạo tự động, không phải khai báo source thông thường.

Bridge method giúp các method có kiểu generic hoặc return type hiệp biến vẫn hoạt động đúng qua ranh giới bytecode.

### 5.1. Bridge method do generic erasure

Xét ví dụ:

~~~java
public class Node<T> {
    public void set(T value) {
        System.out.println(value);
    }
}

public class IntegerNode extends Node<Integer> {
    @Override
    public void set(Integer value) {
        System.out.println(value.intValue());
    }
}
~~~

Ở mức source, IntegerNode override method set(T) với T được thay bằng Integer.

Nhưng method của Node sau erasure là set(Object): void. Method được viết trong IntegerNode là set(Integer): void.

Compiler tạo bridge method có descriptor tương ứng với method đã erasure:

~~~java
// Mã giả minh họa, compiler tự sinh
public void set(Object value) {
    set((Integer) value);
}
~~~

Descriptor của hai method:

~~~text
set(Integer): (Ljava/lang/Integer;)V
set(Object):  (Ljava/lang/Object;)V
~~~

Method bridge có thể có cờ ACC_BRIDGE và ACC_SYNTHETIC. Nó chuyển lời gọi từ descriptor đã erasure sang method cụ thể.

### 5.2. Bridge method do covariant return type

Java cho phép subclass override method với kiểu trả về là subtype của kiểu trả về ở superclass.

~~~java
public class Parent {
    public Object value() {
        return "parent";
    }
}

public class Child extends Parent {
    @Override
    public String value() {
        return "child";
    }
}
~~~

Ở source, Child.value() hợp lệ vì String là subtype của Object. Nhưng descriptor của Parent là ()Ljava/lang/Object;, còn descriptor của Child là ()Ljava/lang/String;.

Để duy trì dispatch cho bytecode tham chiếu tới Parent.value() với return descriptor Object, compiler có thể sinh bridge trong Child:

~~~java
// Mã giả minh họa
public Object value() {
    return value(); // Chuyển tiếp tới method trả về String
}
~~~

Trong class file, method bridge có descriptor của superclass và method thật có descriptor trả về String. Khi kiểm tra bằng javap, có thể thấy hai method cùng tên nhưng descriptor khác nhau.

### 5.3. Vì sao bridge method quan trọng khi phân tích?

Khi dùng reflection hoặc công cụ đọc bytecode, có thể thấy nhiều method cùng tên và gần giống nhau. Không nên mặc định đây là method trùng do lỗi.

Cần kiểm tra:

- Method có cờ bridge không?
- Method có cờ synthetic không?
- Descriptor của method gốc và bridge khác nhau ở đâu?
- Bridge đang duy trì generic override hay covariant return?
- Bytecode consumer đang gọi descriptor nào?

Trong Java Reflection, có thể kiểm tra:

~~~java
for (var method : IntegerNode.class.getDeclaredMethods()) {
    System.out.println(method);
    System.out.println("bridge=" + method.isBridge());
    System.out.println("synthetic=" + method.isSynthetic());
}
~~~

Reflection có thể trả về bridge method cùng method do lập trình viên viết. Các framework quét method nên cân nhắc cờ bridge/synthetic để tránh xử lý cùng một logic hai lần.

## 6. Những thông tin không nằm trong method descriptor

Descriptor chỉ mô tả kiểu tham số và kiểu trả về. Một số thuộc tính khác được lưu ở vị trí khác trong class file hoặc không được JVM dùng để phân biệt method.

| Thông tin | Có nằm trong descriptor? | Vị trí hoặc tác động |
|---|---|---|
| Tên method | Không | name_index riêng trong method_info |
| Kiểu tham số | Có | Phần parameter descriptor |
| Return type | Có | Phần return descriptor |
| Tên tham số | Không | Có thể nằm trong MethodParameters attribute |
| throws clause | Không | Exceptions attribute |
| Generic type | Không đầy đủ | Signature attribute |
| Annotation | Không | RuntimeVisibleAnnotations và các attribute tương ứng |
| public/private/protected | Không | Access flags |
| static | Không | Access flags và loại invocation opcode |
| synchronized | Không | Access flags |
| bridge/synthetic | Không | Access flags |
| varargs | Không | ACC_VARARGS; tham số được biểu diễn bằng array descriptor |

### 6.1. throws clause không thuộc descriptor

Hai khai báo sau có cùng descriptor:

~~~java
public void load(String path) throws IOException {
}

public void load(String path) throws SQLException {
}
~~~

Cả hai đều có descriptor:

~~~text
(Ljava/lang/String;)V
~~~

Java source có thể xử lý khác nhau do checked exception, nhưng JVM method linkage không phân biệt chúng bằng throws clause. Thay đổi throws clause có thể gây ảnh hưởng source compatibility cho consumer khi biên dịch lại, nhưng không làm descriptor thay đổi.

### 6.2. Tên tham số không thuộc descriptor

Ví dụ:

~~~java
public void setName(String name)
public void setName(String username)
~~~

Tên tham số có thể được lưu trong class file nếu compiler phát sinh MethodParameters attribute hoặc thông tin debug phù hợp. Nhưng nó không ảnh hưởng descriptor:

~~~text
(Ljava/lang/String;)V
~~~

Đổi tên tham số không làm bytecode cũ mất liên kết với method.

### 6.3. Varargs và array

Trong Java source:

~~~java
public void log(String... messages)
~~~

Varargs được biểu diễn bằng array ở mức descriptor:

~~~text
([Ljava/lang/String;)V
~~~

Method có cờ ACC_VARARGS, nhưng descriptor giống method nhận String[]:

~~~java
public void log(String[] messages)
~~~

Vì vậy, đổi từ varargs sang array có thể giữ descriptor nhưng thay đổi cách consumer gọi khi biên dịch source. Đây là ví dụ điển hình về khác biệt giữa binary compatibility và source-level API usability.

### 6.4. static và instance method

Modifier static không nằm trong descriptor. Ví dụ:

~~~java
public static int calculate(long value)
~~~

Một method instance có cùng tên, cùng tham số, cùng kiểu trả về sẽ có cùng descriptor:

~~~text
(J)I
~~~

Tuy nhiên, static/instance là thuộc tính class file và ảnh hưởng cách bytecode gọi method:

- invokestatic gọi static method.
- invokevirtual gọi method instance theo class.
- invokeinterface gọi method thông qua interface.
- invokespecial dùng cho constructor, private method hoặc một số lời gọi đặc biệt theo quy tắc JVM.

Thay static thành instance hoặc ngược lại có thể làm bytecode cũ thất bại với IncompatibleClassChangeError, dù descriptor không đổi, vì invocation opcode và kỳ vọng về method kind không còn khớp.

## 7. Descriptor của constructor và field

### 7.1. Constructor

Constructor có tên đặc biệt là <init> và descriptor luôn có kiểu trả về void, ký hiệu V.

Ví dụ:

~~~java
public User(String name, long id) {
}
~~~

Descriptor:

~~~text
(Ljava/lang/String;J)V
~~~

Constructor không có return type trong Java source nhưng class file vẫn biểu diễn phần return descriptor là V.

Class initializer dùng tên đặc biệt <clinit> và descriptor ()V.

### 7.2. Field descriptor

Field không có method descriptor mà có field descriptor, mô tả kiểu của field.

Ví dụ:

~~~java
private long id;
private String name;
private List<String> roles;
~~~

| Field | Descriptor |
|---|---|
| id | J |
| name | Ljava/lang/String; |
| roles | Ljava/util/List; |

Generic type argument của List không xuất hiện trong field descriptor; thông tin generic có thể nằm trong Signature attribute.

Nếu thay kiểu field từ long sang String, descriptor thay từ J thành Ljava/lang/String;. Bytecode cũ tham chiếu field theo owner, tên và descriptor; nếu không còn field phù hợp, có thể gặp NoSuchFieldError.

## 8. Cách xem descriptor bằng công cụ JDK

### 8.1. Dùng javap -s

Biên dịch một class:

~~~java
package com.example;

public class Api {
    public String find(int id, boolean active) {
        return "user";
    }

    public void send(String name, long version, byte[] data) {
    }
}
~~~

Chạy:

~~~bash
javac -d out src/com/example/Api.java
javap -classpath out -p -s com.example.Api
~~~

Kết quả có dạng:

~~~text
public java.lang.String find(int, boolean);
  descriptor: (IZ)Ljava/lang/String;

public void send(java.lang.String, long, byte[]);
  descriptor: (Ljava/lang/String;J[B)V
~~~

Các tùy chọn:

- -p: hiển thị cả thành viên private.
- -s: hiển thị descriptor.
- -v: hiển thị chi tiết class file, access flags và attributes.

### 8.2. Dùng javap -v để xem bridge và generic Signature

Chạy:

~~~bash
javap -classpath out -p -s -v com.example.IntegerNode
~~~

Trong kết quả, tìm các phần:

- descriptor: descriptor nhị phân.
- Signature: metadata generic nếu có.
- ACC_BRIDGE: method bridge.
- ACC_SYNTHETIC: thành phần được compiler sinh tự động.
- Code: bytecode thực thi method.

Khi so sánh hai bản build, hãy giữ output đầy đủ để biết method nào do source khai báo và method nào do compiler sinh.

### 8.3. Xem bytecode instruction gọi method

Dùng:

~~~bash
javap -classpath app.jar -c -v com.example.Consumer
~~~

Một lệnh invoke trong bytecode tham chiếu tới owner, tên và descriptor. Ví dụ về mặt khái niệm:

~~~text
invokevirtual com/example/Api.find:(IZ)Ljava/lang/String;
~~~

Nếu thư viện mới không còn method có symbolic reference tương ứng, JVM có thể ném linkage error khi thực hiện lời gọi.

### 8.4. Công cụ phân tích class file

Ngoài javap, có thể dùng:

- ASM: đọc và ghi class file, tạo method descriptor qua Type.
- Byte Buddy: tạo hoặc biến đổi class/method ở runtime.
- BCEL: đọc và phân tích cấu trúc bytecode.
- Công cụ binary compatibility như japicmp hoặc Revapi: so sánh API giữa các phiên bản thư viện.

Các công cụ này bổ sung cho javap. Khi kết luận, vẫn cần kiểm tra đúng artifact phát hành và thử consumer đã biên dịch với phiên bản cũ.

## 9. Descriptor và binary compatibility khi nâng cấp thư viện

Khi một thư viện thay đổi, cần so sánh descriptor của các method và field công khai/protected mà consumer có thể sử dụng.

| Thay đổi | Descriptor thay đổi? | Rủi ro chính |
|---|---|---|
| Đổi tên tham số | Không | Thường không ảnh hưởng linkage |
| Đổi return type | Có | Bytecode cũ có thể gặp NoSuchMethodError |
| Đổi kiểu tham số | Có | Bytecode cũ tham chiếu descriptor không còn tồn tại |
| Đổi thứ tự tham số | Có | Descriptor thay đổi |
| Thêm overload mới | Descriptor cũ giữ nguyên | Có thể gây source ambiguity khi consumer biên dịch lại |
| Đổi throws clause | Không | Có thể gây source compatibility issue |
| Đổi generic type argument sau erasure | Có thể không | Có thể ảnh hưởng source/generic metadata/behavior |
| Đổi static thành instance | Descriptor không đổi | Có thể gặp IncompatibleClassChangeError |
| Đổi field type | Có | Bytecode cũ có thể gặp NoSuchFieldError |
| Thêm bridge method | Có thêm descriptor | Thường phục vụ tương thích override, cần đọc cờ bridge |

### 9.1. Đổi kiểu tham số

Phiên bản 1:

~~~java
public void send(String message)
~~~

Descriptor:

~~~text
(Ljava/lang/String;)V
~~~

Phiên bản 2:

~~~java
public void send(CharSequence message)
~~~

Descriptor:

~~~text
(Ljava/lang/CharSequence;)V
~~~

Dù String implement CharSequence, descriptor không giống nhau. Bytecode cũ gọi method nhận String và không tự chuyển tham chiếu sang method nhận CharSequence khi liên kết. Nếu method cũ bị xóa, có thể phát sinh NoSuchMethodError.

Một cách migration an toàn hơn là giữ method cũ và thêm overload mới trong một release tương thích:

~~~java
public void send(String message) {
    send((CharSequence) message);
}

public void send(CharSequence message) {
    // Cách triển khai mới
}
~~~

Cách này duy trì descriptor cũ trong giai đoạn chuyển tiếp, nhưng vẫn cần xem xét overload resolution và hành vi.

### 9.2. Thêm overload có thể ảnh hưởng source compatibility

Giả sử ban đầu:

~~~java
public void process(String value) {
}
~~~

Consumer có lời gọi:

~~~java
process(null);
~~~

Sau đó thư viện thêm:

~~~java
public void process(Integer value) {
}
~~~

Khi consumer biên dịch lại, lời gọi process(null) trở nên ambiguous vì null có thể chuyển sang cả String và Integer. Bytecode cũ đã biên dịch trước đó vẫn tham chiếu descriptor của method String nếu method đó còn tồn tại.

Do đó, thêm overload thường giữ binary compatibility nhưng vẫn có thể gây source incompatibility. Đây là lý do cần kiểm thử cả consumer đã biên dịch và consumer biên dịch lại.

## 10. Kiểm chứng bằng consumer cũ và mới

Một cách kiểm chứng thực tế là tạo consumer sử dụng API của thư viện, sau đó thử hai kịch bản.

### Kịch bản A: consumer đã biên dịch với phiên bản thư viện cũ

1. Compile consumer bằng thư viện phiên bản cũ.
2. Giữ nguyên file class consumer.
3. Thay runtime dependency bằng thư viện phiên bản mới.
4. Chạy consumer mà không biên dịch lại.

Nếu method descriptor cũ bị mất hoặc thay đổi, JVM có thể phát sinh linkage error. Đây là phép thử trực tiếp cho binary compatibility.

### Kịch bản B: consumer biên dịch lại với phiên bản mới

1. Dùng source consumer cũ.
2. Thay compile dependency bằng thư viện mới.
3. Compile lại.
4. Chạy test và kiểm tra warning/error.

Kịch bản này phát hiện source incompatibility, ví dụ overload ambiguity, checked exception mới hoặc generic type không còn tương thích.

Hai kịch bản trả lời hai câu hỏi khác nhau. Một thư viện có thể giữ binary compatibility nhưng làm consumer không biên dịch lại được; cũng có thể source code mới compile thành công nhưng bytecode cũ không chạy được.

### 10.1. Giữ đúng artifact trong phép thử

Để kết quả có thể tái hiện:

- Lưu checksum của thư viện cũ và mới.
- Ghi lại JDK compiler và runtime.
- Giữ nguyên class file consumer cũ.
- Kiểm soát classpath để không vô tình nạp thêm bản JAR khác.
- Ghi log đầy đủ khi chạy.
- Xác minh class được nạp từ đúng file JAR.

Có thể dùng class loading log trên các JDK hiện đại:

~~~bash
java -Xlog:class+load=info -cp "consumer.jar:library-new.jar" com.example.Consumer
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy thay vì dấu hai chấm. Tùy JDK, định dạng log có thể khác.

## 11. Quy trình so sánh descriptor giữa hai bản phát hành

Một quy trình phù hợp cho thư viện:

1. Lấy đúng JAR của release cũ và release mới.
2. Liệt kê các class public/protected và các API mà consumer được phép dùng.
3. Chạy javap -p -s trên các class cần so sánh.
4. Ghi lại method name, descriptor, field descriptor và access flags.
5. Phân biệt method do source khai báo với bridge/synthetic method.
6. So sánh generic Signature attribute nếu thay đổi generic API.
7. Xem các thay đổi static/instance, visibility và throws riêng.
8. Chạy công cụ binary compatibility để mở rộng kiểm tra toàn bộ API.
9. Chạy consumer đã biên dịch bằng release cũ với release mới.
10. Biên dịch lại consumer trên release mới và chạy regression test.

Không nên chỉ so sánh file javap dạng text theo tên method. Cần parse descriptor và flags, vì thứ tự hiển thị hoặc định dạng có thể thay đổi theo JDK.

## 12. Những nhầm lẫn thường gặp

- **Nhầm signature với descriptor:** source signature không bao gồm return type, nhưng method descriptor có.
- **Nghĩ generic nằm đầy đủ trong descriptor:** type arguments bị erasure; generic metadata được lưu riêng.
- **Nghĩ throws clause thay đổi descriptor:** throws clause không nằm trong descriptor.
- **Nghĩ tên tham số ảnh hưởng linkage:** tên tham số không phải thành phần của descriptor.
- **Nghĩ varargs khác array ở descriptor:** varargs được biểu diễn bằng array; cờ ACC_VARARGS nằm riêng.
- **Nghĩ static nằm trong descriptor:** static là access flag và ảnh hưởng invocation opcode.
- **Nghĩ hai method cùng tên luôn là overload hợp lệ trong Java:** return type đơn thuần không tạo overload ở source, dù JVM descriptor có chứa return type.
- **Nghĩ bridge method là code trùng lỗi:** bridge thường là cơ chế compiler cần để giữ override sau erasure hoặc covariant return.
- **Nghĩ descriptor không đổi là không có breaking change:** source, generic metadata, checked exception và behavioral contract vẫn có thể đổi.
- **Nghĩ build thành công là đủ:** consumer bytecode cũ cần được chạy với artifact mới để kiểm tra linkage thực tế.

## 13. Checklist kiểm tra

### Source signature và descriptor

- [ ] Đã phân biệt source-level method signature với JVM method descriptor.
- [ ] Đã xác định descriptor của method công khai/protected quan trọng.
- [ ] Đã xác định descriptor của constructor và field liên quan.
- [ ] Đã kiểm tra kiểu trả về vì return type nằm trong descriptor.
- [ ] Đã phân biệt descriptor với generic Signature attribute.
- [ ] Đã ghi nhận các method bridge và synthetic.

### Binary compatibility

- [ ] Đã so sánh descriptor giữa release cũ và mới.
- [ ] Đã kiểm tra thay đổi tham số, return type và field type.
- [ ] Đã kiểm tra static/instance và access flags.
- [ ] Đã đánh giá ảnh hưởng của throws clause và generic metadata ở source level.
- [ ] Đã kiểm tra overload mới có gây ambiguous call khi compile lại không.
- [ ] Đã chạy consumer cũ với thư viện mới.
- [ ] Đã compile lại consumer với thư viện mới.

### Bằng chứng

- [ ] Đã dùng javap -p -s hoặc công cụ đọc class file.
- [ ] Đã lưu descriptor và checksum của artifact.
- [ ] Đã kiểm soát classpath và xác nhận đúng JAR được nạp.
- [ ] Đã lưu log linkage error hoặc kết quả test.
- [ ] Đã xác định phương án migration cho từng descriptor bị thay đổi.

## Kết luận

Method signature ở mức Java source và method descriptor ở mức JVM phục vụ hai tầng khác nhau. Source signature không dùng return type để phân biệt overload, trong khi descriptor mô tả cả tham số lẫn kiểu trả về. Generic type được erasure trước khi tạo descriptor; bridge method có thể được compiler sinh để duy trì override; các thuộc tính như throws, tên tham số, annotation và static được lưu hoặc xử lý ở nơi khác.

Khi đánh giá binary compatibility, hãy đọc descriptor từ artifact thực tế, so sánh cả access flags và metadata liên quan, rồi chạy consumer đã biên dịch với phiên bản thư viện cũ trên phiên bản mới. Kết hợp phép thử đó với compile lại consumer sẽ cho thấy rõ cả binary compatibility lẫn source compatibility.

