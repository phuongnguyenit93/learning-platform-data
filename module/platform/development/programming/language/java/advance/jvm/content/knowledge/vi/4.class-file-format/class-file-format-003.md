# Tên nhị phân, tên nội bộ và descriptor của trường, phương thức, mảng

## 1. Vì sao phải phân biệt những cách biểu diễn tên?

Trong Java, một lớp có thể được nhắc đến dưới nhiều hình thức:

~~~text
Mã nguồn Java:             java.lang.String
Tên nhị phân (binary):     java.lang.String
Tên nội bộ JVM (internal): java/lang/String
Descriptor kiểu tham chiếu: Ljava/lang/String;
Descriptor mảng String[]:  [Ljava/lang/String;
~~~

Những chuỗi này **không hoán đổi tùy ý**. Chúng phục vụ những vai trò khác nhau trong Java source, Java Virtual Machine Specification (JVMS), tệp **.class**, công cụ đọc bytecode và Reflection API. Sự nhầm lẫn thường chỉ lộ ra khi viết code xử lý bytecode, tìm lớp bằng reflection, sinh proxy, dùng instrumentation, truy vấn phương thức theo descriptor hoặc giải thích thông tin constant pool.

Sau bài học, bạn có thể:

- Nhận diện tên nhị phân, tên nội bộ và tên canonical/source của lớp thông thường và lớp lồng nhau.
- Đọc và tự tạo **field descriptor** cho primitive, tham chiếu và mảng một hay nhiều chiều.
- Đọc và tự tạo **method descriptor**, bao gồm danh sách tham số, kiểu trả về và **void**.
- Giải thích vì sao **java.lang.String**, **java/lang/String**, **Ljava/lang/String;** và **[Ljava.lang.String;** xuất hiện ở những API/ngữ cảnh khác nhau.
- Hiểu cách các tên/descriptor xuất hiện trong **CONSTANT_Class**, **CONSTANT_NameAndType**, **CONSTANT_Fieldref** và **CONSTANT_Methodref**.
- Kiểm tra kết quả bằng **javap -s -p -v**, **Class.getName()**, **Class.getCanonicalName()**, **Class.forName()** và **MethodType**.

Trọng tâm là ý nghĩa chính xác của định dạng class file; bài học dùng Java 17+ để minh họa.

## 2. Tên trong Java: source, canonical và binary name

### 2.1. Tên nhị phân (binary name) là gì?

**Binary name** là tên được Java Language Specification (JLS, §13.1) định nghĩa để định danh kiểu lớp/interface theo những quy tắc sử dụng ở dạng nhị phân. Với lớp top-level phổ biến, tên nhị phân giống tên đầy đủ thường thấy trong mã nguồn:

~~~text
java.lang.String
java.util.Map
com.example.app.Customer
~~~

Dấu chấm **.** phân tách thành phần package. Với một **member class** được khai báo trong lớp khác, binary name dùng **$** để ghép tên nhị phân của lớp bao ngoài và tên đơn giản của lớp thành viên:

~~~java
// Ví dụ mô tả cấu trúc khai báo:
package com.example.app;

class Outer {
    static class Inner {}
}
~~~

~~~text
Tên source/canonical của member class: com.example.app.Outer.Inner
Tên binary của member class:          com.example.app.Outer$Inner
Tên binary của top-level class:       com.example.app.Outer
~~~

Không phải mọi ký tự **$** đều chứng minh có lớp lồng nhau: Java cho phép **$** trong identifier, và các lớp local/anonymous có quy tắc binary name riêng do compiler tạo. Cũng đừng dùng quy tắc “thay mọi dấu chấm bằng $” để biến source name thành binary name: dấu chấm package vẫn là dấu chấm.

Tên nhị phân còn gắn với danh tính lớp ở runtime cùng **defining class loader**; hai class loader khác nhau có thể định nghĩa các lớp có cùng binary name mà JVM vẫn coi là những runtime class khác nhau.

### 2.2. Canonical name không đồng nghĩa binary name

**Canonical name** là cách viết tên theo quy tắc ngôn ngữ Java cho những kiểu có canonical name. Với member class, cách viết này dùng dấu chấm giữa **Outer** và **Inner**; binary name dùng **$**.

Reflection thường cho thấy:

| Lớp | **Class.getName()** | **Class.getCanonicalName()** |
| --- | --- | --- |
| **java.lang.String** | **java.lang.String** | **java.lang.String** |
| **Outer.Inner** | **Outer$Inner** (nếu không có package) | **Outer.Inner** |
| **int** | **int** | **int** |
| **String[]** | **[Ljava.lang.String;** | **java.lang.String[]** |
| **int[][]** | **[[I** | **int[][]** |

**getCanonicalName()** có thể trả **null** cho lớp local hoặc anonymous không có canonical name. **getName()** của mảng dùng một biểu diễn dạng descriptor nhưng **tên reference component được viết bằng dấu chấm**, khác với object descriptor trong class file dùng dấu gạch chéo. Phần sau sẽ giải thích rõ.

### 2.3. Internal name: tên nội bộ của JVM

Khi biểu diễn binary name của lớp/interface trong những cấu trúc class file cần **internal form**, JVMS thay các dấu chấm package **.** thành dấu gạch chéo **/**.

~~~text
Binary name:   java.lang.String
Internal name: java/lang/String

Binary name:   com.example.app.Outer$Inner
Internal name: com/example/app/Outer$Inner
~~~

**Dấu $ của member class được giữ nguyên**, không đổi thành dấu gạch chéo. **/** trong internal name là dấu phân tách thành phần package/class theo ngữ pháp JVM, **không phải lời cam kết đường dẫn tệp thực trên ổ đĩa**.

Ví dụ, trong một JAR, entry **com/example/app/Outer$Inner.class** thường tương ứng với lớp đó; nhưng việc thực thi có thể dùng module, class loader tùy biến, byte array hay các nguồn lớp khác. Internal name là khái niệm định danh trong class file, không nên đồng nhất nó với API filesystem.

## 3. Ba chuỗi dễ bị dùng sai

Xét kiểu **java.lang.String**:

| Chuỗi | Vai trò đúng | Dùng ở đâu? |
| --- | --- | --- |
| **java.lang.String** | Binary name | **Class.forName("java.lang.String")**, metadata/tên lớp theo quy tắc Java |
| **java/lang/String** | Internal name của lớp | **CONSTANT_Class** cho non-array class; phần tên lớp bên trong object descriptor |
| **Ljava/lang/String;** | Field descriptor của một tham chiếu đến String | **field_info.descriptor_index**; tham số/kiểu trả về của method descriptor |

**Tiền tố L và dấu ;** là thành phần ngữ pháp descriptor của một **object/reference type**. Vì vậy **java/lang/String** riêng lẻ **không phải field descriptor** và **Ljava/lang/String;** **không phải internal name của class**.

Một số công cụ bytecode nhận tham số tên dưới dạng internal name, còn API reflection nhận binary name. Trước khi truyền một chuỗi tên vào thư viện, phải đọc rõ contract: một API yêu cầu **owner internal name**, một API khác yêu cầu **type descriptor**, và API khác nữa cần **binary name**. Chuyển đổi giữa chúng chỉ được thực hiện theo đúng loại dữ liệu.

## 4. Descriptor là gì trong class file?

**Descriptor** là chuỗi cú pháp ngắn gọn biểu diễn **kiểu của field** hoặc **tập tham số và kiểu trả về của method**. Chuỗi descriptor được lưu trong constant pool dưới dạng chuỗi UTF-8 biến thể theo định dạng class file; các cấu trúc **field_info**, **method_info** hoặc **NameAndType** tham chiếu đến nó bằng chỉ số.

Đặc tả JVMS phân biệt:

- **Field descriptor**: biểu diễn một kiểu giá trị, bao gồm primitive, object/reference hoặc array.
- **Method descriptor**: biểu diễn lần lượt các kiểu tham số trong **(...)** rồi đến kiểu trả về.
- **Generic signature**: thông tin bổ sung về generic type arguments/type variables; dùng ngữ pháp **Signature** khác descriptor thông thường.

Descriptor là dữ liệu mang ý nghĩa thực thi/liên kết; **generic signature không thay thế descriptor**.

## 5. Bảng mã field descriptor cho primitive

Mỗi kiểu primitive dùng đúng một ký tự ASCII:

| Kiểu Java | Descriptor | Ví dụ trường |
| --- | --- | --- |
| **byte** | **B** | **byte count** → **B** |
| **char** | **C** | **char initial** → **C** |
| **double** | **D** | **double score** → **D** |
| **float** | **F** | **float ratio** → **F** |
| **int** | **I** | **int age** → **I** |
| **long** | **J** | **long total** → **J** |
| **short** | **S** | **short level** → **S** |
| **boolean** | **Z** | **boolean active** → **Z** |

Hai điều cần nhớ:

1. **J** là mã của **long**, không phải **L**. Ký tự **L** dành cho kiểu tham chiếu object.
2. **V** biểu diễn **void** khi nó đứng ở **vị trí kiểu trả về của method**; **void không phải kiểu field**, cũng không được làm thành phần của array descriptor.

Ví dụ **int** là **I**, không phải **int**; **boolean** là **Z**, không phải **B** hay **boolean**.

Các ký tự descriptor nhận diện **kiểu khai báo**. Việc JVM dùng computational **int** cho nhiều lệnh thao tác với byte/short/char/boolean không làm các descriptor **B/S/C/Z** trở thành **I**.

## 6. Descriptor của kiểu tham chiếu đối tượng

Ngữ pháp object type:

~~~text
L<internal-name>;
~~~

Trong đó **L** là ký tự bắt đầu, **internal-name** dùng dấu **/** và dấu **;** kết thúc kiểu.

Ví dụ:

| Kiểu Java | Internal name | Field descriptor |
| --- | --- | --- |
| **String** | **java/lang/String** | **Ljava/lang/String;** |
| **Object** | **java/lang/Object** | **Ljava/lang/Object;** |
| **java.util.List** | **java/util/List** | **Ljava/util/List;** |
| **com.example.Customer** | **com/example/Customer** | **Lcom/example/Customer;** |
| **com.example.Outer.Inner** | **com/example/Outer$Inner** | **Lcom/example/Outer$Inner;** |

Với **Lcom/example/Outer$Inner;**:

~~~text
L        com/example/Outer$Inner       ;
^        ^                              ^
bắt đầu  internal binary name           kết thúc object descriptor
~~~

Không viết **Lcom.example.Outer.Inner;** trong class-file descriptor. Dấu chấm giữa **Outer.Inner** của canonical/source name cũng không thay thế được **$** của member-class binary name.

### 6.1. Các tên không đủ điều kiện (unqualified names)

Tên field hoặc tên method được lưu dưới dạng **unqualified name**, ví dụ **count**, **parse**, **equals**. Chúng không chứa dấu **.**, **;**, **[**, **/**; phần lớn method name còn bị hạn chế **<** và **>**, ngoại trừ tên đặc biệt **<init>** và **<clinit>**.

Tên field hoặc tên method **không được gộp cùng descriptor thành một chuỗi trong class file**. Chúng xuất hiện ở các mục riêng: tên **count** + descriptor **I**, hoặc tên **accept** + descriptor **(I)Z**. Cách trình bày kiểu **accept(I)Z** thường gặp trong tài liệu/log là cách ghép để dễ đọc, không phải cú pháp field descriptor.

## 7. Descriptor của mảng: thêm một dấu [ cho mỗi chiều

**Array descriptor** được tạo bằng một hoặc nhiều ký tự **[** đứng trước descriptor của loại phần tử cuối cùng. Mỗi dấu **[** tương ứng với một chiều.

~~~text
T[]     -> [ + descriptor(T)
T[][]   -> [[ + descriptor(T)
T[][][] -> [[[ + descriptor(T)
~~~

Ví dụ:

| Java type | Array descriptor | Cách đọc |
| --- | --- | --- |
| **int[]** | **[I** | Mảng một chiều, thành phần là int |
| **int[][]** | **[[I** | Mảng hai chiều, thành phần cuối là int |
| **boolean[]** | **[Z** | Mảng boolean một chiều |
| **byte[][]** | **[[B** | Mảng byte hai chiều |
| **String[]** | **[Ljava/lang/String;** | Mảng String một chiều |
| **String[][]** | **[[Ljava/lang/String;** | Mảng String hai chiều |
| **Outer.Inner[]** | **[Lcom/example/Outer$Inner;** | Mảng member class một chiều |
| **double[][][]** | **[[[D** | Mảng double ba chiều |

**Vị trí dấu [ quan trọng:** descriptor **[I** (int[]) khác **I** (int); **[[I** (int[][]) cũng khác **[I** (int[]). Trong Java, mảng nhiều chiều thực chất là mảng chứa các phần tử là mảng; descriptor biểu diễn cấp lồng, không quy định mọi hàng phải có cùng độ dài.

**Giới hạn class file:** một array type descriptor hợp lệ có tối đa **255 chiều**; điều này không có nghĩa ứng dụng nên hoặc có đủ RAM để tạo mảng 255 chiều. Không thể tạo mảng kiểu **void[]** hay descriptor **[V**.

### 7.1. Mảng tham chiếu: dấu chấm hay dấu gạch chéo?

Phân biệt rất cẩn thận ba cách ghi:

~~~text
Kiểu source:
    java.lang.String[]

Field descriptor trong class file:
    [Ljava/lang/String;

Class.getName() của String[].class:
    [Ljava.lang.String;
~~~

**Class.getName()** đặc biệt: với mảng tham chiếu, nó sử dụng **dấu chấm trong phần tên binary của component type**, trong khi descriptor của mảng trong class file dùng **internal name với dấu /**. Hai biểu diễn trông gần giống nhau nhưng khác chuỗi ký tự.

Với primitive array, không có tên package phải chuyển đổi nên **int[]** cho chuỗi **[I** ở cả dạng array descriptor lẫn **getName()**.

### 7.2. Mảng cũng có Class object

Một đối tượng lớp mảng có thể được nhận qua **String[].class** hoặc **int[][].class**, và có tên hiển thị theo quy tắc runtime. Đây không làm phát sinh nguồn Java khai báo lớp **[I**. Các kiểu mảng là kiểu runtime riêng, và class file constant pool có thể chứa **CONSTANT_Class** mang tên mảng ở dạng descriptor, như **[Ljava/lang/String;**.

Đối với **CONSTANT_Class**:
- Nếu tham chiếu đến lớp/interface thông thường, chuỗi tên thường là **internal form**, ví dụ **java/lang/String**.
- Nếu tham chiếu đến array class, chuỗi biểu diễn **array descriptor**, ví dụ **[Ljava/lang/String;**.

Do vậy, khẳng định “mọi **CONSTANT_Class** đều chứa một internal name không có dấu [” là sai. Đây là khác biệt rất đáng kiểm tra khi đọc constant pool.

## 8. Method descriptor: (tham số)kiểu trả về

Ngữ pháp cốt lõi:

~~~text
MethodDescriptor:
    ( ParameterDescriptor* ) ReturnDescriptor

ParameterDescriptor:
    FieldType

ReturnDescriptor:
    FieldType | V
~~~

Nghĩa là: dấu **(**, nối trực tiếp các field descriptor của tất cả tham số **theo đúng thứ tự**, dấu **)**, rồi một descriptor của kiểu trả về hoặc **V** cho **void**.

Không có dấu phẩy hoặc khoảng trắng phân cách tham số trong descriptor chuẩn.

| Khai báo Java | Method descriptor |
| --- | --- |
| **void run()** | **()V** |
| **int sum(int a, int b)** | **(II)I** |
| **boolean valid(String text)** | **(Ljava/lang/String;)Z** |
| **String join(String a, String b)** | **(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;** |
| **long convert(int n, double d)** | **(ID)J** |
| **String[] lookup(int[] ids, String[][] names)** | **([I[[Ljava/lang/String;)[Ljava/lang/String;** |
| **void accept(boolean[] flags, long n)** | **([ZJ)V** |
| **Object identity(Object x)** | **(Ljava/lang/Object;)Ljava/lang/Object;** |

Phân tích ví dụ:

~~~text
([I[[Ljava/lang/String;)[Ljava/lang/String;
 | |                | |  
 | +-- int[]       | +-- String[] (return)
 +-- parameter 1   +-- parameter 2 is String[][]
~~~

Chính xác hơn, nội dung giữa dấu ngoặc **(** và **)** gồm hai tham số nối liền: **[I** và **[[Ljava/lang/String;**. Sau dấu **)** là **[Ljava/lang/String;**. Với ký tự **;**, phải biết nó kết thúc object descriptor; các ký tự tiếp theo có thể là descriptor của tham số tiếp theo.

### 8.1. Kiểu trả về là một phần của method descriptor

Hai method descriptors **(I)I** và **(I)J** khác nhau vì kiểu trả về khác nhau. JVM có thể phân biệt thông tin symbolic reference ở mức tên và descriptor; còn **Java source không cho overload một phương thức chỉ bằng cách thay kiểu trả về**.

~~~java
// Hai khai báo này trong cùng một lớp là lỗi ở Java source:
// int find(int id)  { return id; }
// long find(int id) { return id; }
~~~

Không được suy luận luật overload của ngôn ngữ Java hoàn toàn giống mọi quy tắc cấu trúc của tệp class. Tên method và descriptor cùng tham gia định danh/lien kết bytecode; compile-time rules của Java còn phụ thuộc signature/overload resolution.

### 8.2. Tham số this có nằm trong descriptor?

Không. Với phương thức instance, **this** được truyền ngầm bởi instruction gọi phương thức, **không có descriptor tham số this đứng ở đầu**.

~~~java
class Account {
    int deposit(int amount) {
        return amount;
    }
}
~~~

Method descriptor của **deposit** là **(I)I**, **không phải** **(LAccount;I)I**.

Khi xem bytecode của method instance, local slot 0 thường chứa **this**, nhưng layout local variables không biến **this** thành một tham số explicit của method descriptor.

### 8.3. Giới hạn số slot của tham số

JVMS giới hạn tổng **parameter length** của method descriptor ở **255 đơn vị**. Tham số **long** và **double** mỗi cái tính **2**; những kiểu còn lại, kể cả array/reference, tính **1**. Với invocation của phương thức instance/interface, giới hạn còn tính thêm **this** ngầm **1** đơn vị, dù **this** không xuất hiện trong chuỗi descriptor.

Đây là giới hạn của mô hình JVM, **không** phải giới hạn số ký tự văn bản của descriptor.

## 9. Nằm ở đâu trong class file và constant pool?

Một class file có cấu trúc **constant_pool**, rồi các bảng khai báo field và method. Ở mức tối giản:

~~~text
ClassFile
  constant_pool
    CONSTANT_Utf8        "demo/names/NameDemo"
    CONSTANT_Class       -> Utf8 internal name
    CONSTANT_Utf8        "count"
    CONSTANT_Utf8        "I"
    CONSTANT_Utf8        "check"
    CONSTANT_Utf8        "(I[Ljava/lang/String;)Z"
    CONSTANT_NameAndType -> name + descriptor
    CONSTANT_Fieldref    -> class + name_and_type
    CONSTANT_Methodref   -> class + name_and_type
  fields[]
    field_info
      name_index        -> "count"
      descriptor_index  -> "I"
  methods[]
    method_info
      name_index        -> "check"
      descriptor_index  -> "(I[Ljava/lang/String;)Z"
~~~

Sơ đồ thể hiện **vai trò** của các phần tử, không phải offset thực của một class file cụ thể. Constant pool dùng nhiều loại entry có quan hệ bằng chỉ số; một field declaration không nhất thiết tự có **Fieldref** trỏ ngược đến chính nó. **Fieldref/Methodref** xuất hiện khi có symbolic reference tương ứng (chẳng hạn một lệnh bytecode cần tham chiếu field/method).

Trong class file:
- **field_info** lưu **tên riêng** và **field descriptor**.
- **method_info** lưu **tên riêng** và **method descriptor**.
- **CONSTANT_NameAndType** ghép tên thành viên với descriptor để sử dụng trong symbolic reference và các cấu trúc khác.
- **CONSTANT_Fieldref**, **CONSTANT_Methodref** hoặc **CONSTANT_InterfaceMethodref** kết hợp owner class/interface và **NameAndType**.
- **CONSTANT_Class** thường chỉ tới internal name của class hoặc array descriptor, tùy đối tượng tham chiếu.

### 9.1. Ví dụ giải nghĩa một lời gọi

Giả sử mã Java:

~~~java
// Mã minh họa; cần lớp java.lang.String và đoạn mã trong một phương thức:
int length = "Java".length();
~~~

Symbolic reference của phương thức **String.length()** mô tả:

~~~text
Owner class internal name: java/lang/String
Method name:               length
Method descriptor:         ()I
~~~

Cách ghi quen thuộc:

~~~text
java/lang/String.length:()I
~~~

Đây là **ký pháp trình bày một symbolic reference**, chứ không phải một string method descriptor đơn lẻ. Descriptor chỉ là **()I**; owner và tên phương thức là thành phần riêng.

### 9.2. Phương thức khởi tạo

Constructor thường xuất hiện trong class file với method name **<init>** và descriptor kết thúc bằng **V**, chẳng hạn:

~~~text
<init>(Ljava/lang/String;I)V
~~~

Tên đặc biệt **<clinit>** biểu diễn phương thức khởi tạo lớp/interface trong class file, có descriptor **()V** theo quy tắc của JVM. Đây không phải những method được viết trực tiếp với tên **<init>** hoặc **<clinit>** trong Java source.

## 10. Ví dụ Java 17+ độc lập để quan sát tên và descriptor

Tạo cấu trúc tệp:

~~~text
demo/
  names/
    NameDemo.java
~~~

Nội dung của **demo/names/NameDemo.java**:

~~~java
package demo.names;

import java.lang.invoke.MethodType;

public class NameDemo {
    private int count;
    private String[] titles;
    private int[][] grid;
    private Item item;

    public static class Item {
    }

    public static boolean check(int limit, String[] names) {
        return limit > 0 && names != null;
    }

    public static String[] convert(int[] ids, Item item) {
        return new String[] {String.valueOf(ids.length), item.getClass().getSimpleName()};
    }

    public static void main(String[] args) {
        Class<?> nested = Item.class;
        Class<?> nestedArray = Item[][].class;

        System.out.println("outer=" + NameDemo.class.getName());
        System.out.println("nestedBinary=" + nested.getName());
        System.out.println("nestedCanonical=" + nested.getCanonicalName());

        System.out.println("arrayGetName=" + nestedArray.getName());
        System.out.println("arrayCanonical=" + nestedArray.getCanonicalName());
        System.out.println("intArrayGetName=" + int[][].class.getName());
        System.out.println("stringArrayGetName=" + String[].class.getName());

        MethodType method = MethodType.methodType(
                boolean.class, int.class, String[].class);
        System.out.println("methodDescriptor=" + method.toMethodDescriptorString());
    }
}
~~~

Từ thư mục **chứa folder demo**, sử dụng JDK 17+:

~~~bash
mkdir out
javac -encoding UTF-8 -d out demo/names/NameDemo.java
java -cp out demo.names.NameDemo
~~~

Nếu **out** đã tồn tại, bỏ qua lệnh **mkdir out**. Kết quả **stdout của chương trình**:

~~~text
outer=demo.names.NameDemo
nestedBinary=demo.names.NameDemo$Item
nestedCanonical=demo.names.NameDemo.Item
arrayGetName=[[Ldemo.names.NameDemo$Item;
arrayCanonical=demo.names.NameDemo.Item[][]
intArrayGetName=[[I
stringArrayGetName=[Ljava.lang.String;
methodDescriptor=(I[Ljava/lang/String;)Z
~~~

Giải thích kết quả:

1. **getName()** của lớp thường/member class trả **binary name** với dấu chấm package và dấu **$** giữa nested member class.
2. **getCanonicalName()** của member class dùng dấu **.** giữa lớp ngoài/lớp trong.
3. **Item[][].class.getName()** có tiền tố **[[** và phần reference component dùng tên binary với **dấu chấm**: **[[Ldemo.names.NameDemo$Item;**.
4. **Item[][].class.getCanonicalName()** hiển thị dạng source **demo.names.NameDemo.Item[][]**.
5. Mảng primitive **int[][]** dùng **[[I**.
6. **MethodType.toMethodDescriptorString()** cung cấp descriptor đúng theo cú pháp class file: **(I[Ljava/lang/String;)Z**. Phương thức **check** có đúng tham số và kiểu trả về như vậy.

Các field khai báo để quan sát trong bytecode; không cần gán giá trị runtime để **javap** hiển thị descriptor.

### 10.1. Xem field và method descriptors bằng javap

Chạy:

~~~bash
javap -classpath out -p -s demo.names.NameDemo
javap -classpath out -p -s 'demo.names.NameDemo$Item'
~~~

Trong một số shell (như PowerShell), dấu nháy đơn bao quanh tên lớp chứa **$** giúp ngăn cơ chế nội suy biến. Cú pháp quote cần điều chỉnh theo shell đang dùng; với Bash cũng có thể dùng dấu nháy đơn như trên.

Ở kết quả của class **NameDemo**, hãy tìm những cặp tên/descriptor:

~~~text
private int count;
  descriptor: I

private java.lang.String[] titles;
  descriptor: [Ljava/lang/String;

private int[][] grid;
  descriptor: [[I

private demo.names.NameDemo$Item item;
  descriptor: Ldemo/names/NameDemo$Item;

public static boolean check(int, java.lang.String[]);
  descriptor: (I[Ljava/lang/String;)Z

public static java.lang.String[] convert(int[], demo.names.NameDemo$Item);
  descriptor: ([ILdemo/names/NameDemo$Item;)[Ljava/lang/String;
~~~

Đây là **những dòng trọng tâm cần đối chiếu**, không cam kết mọi phần của output **javap** giống hệt giữa các phiên bản/cách biên dịch. Kiểu được trình bày trong dòng khai báo theo cách dễ đọc; chuỗi sau **descriptor:** tuân theo cú pháp JVM.

### 10.2. Xem constant pool và symbolic references

Chạy:

~~~bash
javap -classpath out -v -p demo.names.NameDemo
~~~

Tìm các chuỗi tương tự:

~~~text
demo/names/NameDemo
demo/names/NameDemo$Item
java/lang/String
(I[Ljava/lang/String;)Z
([ILdemo/names/NameDemo$Item;)[Ljava/lang/String;
~~~

Với **-v**, output có thông tin class file, constant pool, các attributes và code; số thứ tự **#n**, vị trí constant pool và các phần phụ khác có thể thay đổi. Quan sát mối liên hệ giữa **Class**, **Utf8**, **NameAndType** và các method/field references thay vì học thuộc các chỉ số.

### 10.3. Đọc bytecode mà không nhầm tên

Một dòng disassembly có thể hiển thị:

~~~text
Method java/lang/String.valueOf:(I)Ljava/lang/String;
~~~

Dòng này chứa **owner internal name** (java/lang/String), **method name** (valueOf) và **method descriptor** ((I)Ljava/lang/String;). Khi được hiển thị cùng nhau, chúng vẫn là ba thành phần có ngữ nghĩa độc lập.

## 11. Reflection API và cách nạp lớp theo tên

Java Reflection cung cấp nhiều phép nhìn tên, nhưng **các phép này không đồng nhất về định dạng chuỗi**.

| API | Dùng cho | Ví dụ |
| --- | --- | --- |
| **Class.getName()** | Binary name của class thường; encoding đặc biệt cho array class | **String.class.getName()** → **java.lang.String** |
| **Class.getCanonicalName()** | Canonical name khi có | **String[].class.getCanonicalName()** → **java.lang.String[]** |
| **Class.getSimpleName()** | Tên ngắn, thân thiện hơn | **NameDemo.Item.class.getSimpleName()** → **Item** |
| **Class.getTypeName()** | Tên kiểu để trình bày, array có dấu **[]** | **String[][].class.getTypeName()** → **java.lang.String[][]** |
| **Class.forName(String)** | Tìm lớp bằng tên binary (hoặc array-name encoding hỗ trợ) | **Class.forName("java.lang.String")** |
| **MethodType.toMethodDescriptorString()** | Descriptor của loại phương thức | **MethodType.methodType(void.class, int.class)** → **(I)V** |

Với member class, **Class.forName** dùng binary name chứa **$**:

~~~java
// Đoạn minh họa đặt trong một phương thức có throws ClassNotFoundException:
Class<?> c = Class.forName("demo.names.NameDemo$Item");
~~~

Chuỗi **demo.names.NameDemo.Item** là canonical/source name và **không** thay thế binary name của member class cho **Class.forName**.

### 11.1. Class.forName và tên mảng

Với array class, **Class.forName** nhận chuỗi mã hóa tên array giống định dạng **Class.getName()**:

~~~java
// Đoạn minh họa, có thể ném ClassNotFoundException:
Class<?> strings = Class.forName("[Ljava.lang.String;");
Class<?> ints2d = Class.forName("[[I");
Class<?> nested2d = Class.forName("[[Ldemo.names.NameDemo$Item;");
~~~

Chú ý **[Ljava.lang.String;** dùng **dấu chấm** trong tên binary component. Đưa chuỗi descriptor class-file **[Ljava/lang/String;** trực tiếp vào **Class.forName** là sai định dạng tên trong API này.

Không dùng **Class.forName("int[]")** hoặc **Class.forName("[Ljava/lang/String;")** theo thói quen khi chưa xác định contract: lớp array có kiểu tên đặc biệt, còn **int[].class** là cách biểu đạt trực tiếp và an toàn trong mã nguồn.

### 11.2. Khi nào cần chuyển tên?

- Từ **binary name của lớp thường** sang internal name: thay **dấu chấm package** thành **/** và giữ **$** của member class.
- Từ internal name lớp tham chiếu sang field descriptor: ghép **L** + internal name + **;**.
- Từ descriptor của kiểu thành mảng: thêm **[** cho mỗi chiều.
- Từ descriptor trở lại loại Java: cần parser tuân theo grammar, không đủ dùng thao tác thay dấu chấm đơn giản.
- Với reflection, nên thao tác trên **Class<?>**, **Method**, **MethodType** và API chuẩn khi có thể; chỉ tạo chuỗi descriptor thủ công khi thực sự cần tích hợp định dạng JVM/bytecode tooling.

## 12. Generic signature không giống descriptor

Giả sử có field:

~~~java
// Mã minh họa một field của lớp:
java.util.List<String> names;
~~~

**Field descriptor** vẫn là:

~~~text
Ljava/util/List;
~~~

Thông tin **String** là type argument không xuất hiện trong descriptor cơ bản, vì Java generics chủ yếu dựa vào **type erasure**. Nếu class file giữ metadata generic phù hợp, **Signature** attribute sẽ mang biểu diễn generic (chẳng hạn **Ljava/util/List<Ljava/lang/String;>;**).

Tương tự, hai phương thức **List<String>** và **List<Integer>** ở tham số không trở thành hai overload Java hợp lệ chỉ nhờ khác generic type arguments, vì erasure dẫn đến cùng parameter type/signature ở tầng kiểm tra tương ứng.

Phân biệt các thuật ngữ:

| Thuật ngữ | Nó chứa gì? |
| --- | --- |
| **Descriptor** | Kiểu field hoặc kiểu tham số/trả về được JVM sử dụng cho linking/execution |
| **Signature attribute** | Thông tin generic parameterized types, type variables, bounds trong những khai báo có dữ liệu generic |
| **Method name** | Tên riêng, ví dụ **find** |
| **Binary/internal name** | Tên lớp/interface, không phải toàn bộ kiểu phương thức |
| **Source declaration** | Cú pháp Java gồm modifiers, generic arguments, tên tham số... mà descriptor không lưu đầy đủ |

Đừng lấy chuỗi generic signature đưa vào nơi yêu cầu field descriptor; dấu **<...>** thuộc grammar khác và có thể khiến thư viện bytecode từ chối đầu vào.

## 13. Cách tự đọc và dựng descriptor không cần công cụ

Hãy làm theo thứ tự:

**Với field:**

1. Xác định kiểu Java sau khi bỏ qua tên biến, modifier và generic arguments đối với descriptor thông thường.
2. Nếu là primitive, chuyển sang một ký tự **B/C/D/F/I/J/S/Z**.
3. Nếu là class/interface, tìm **binary name** chính xác (đặc biệt với nested class), chuyển sang internal name rồi bọc **L...;**.
4. Nếu là array, đếm số **[]** và thêm số lượng dấu **[** tương ứng trước descriptor của component type.

Ví dụ:

~~~text
java.util.Map.Entry<String, Integer>[] entries
    -> raw member class: java.util.Map$Entry
    -> internal name:    java/util/Map$Entry
    -> field descriptor: [Ljava/util/Map$Entry;
~~~

**Với method:**

1. Đọc lần lượt từng tham số và tạo field descriptor cho chúng.
2. Nối tất cả **không có dấu phẩy** bên trong **(...)**.
3. Sau **)**, thêm field descriptor của return type hoặc **V** nếu **void**.
4. Không thêm tham số **this** chỉ vì method là instance.
5. Không đưa tên method, tên tham số, **throws** hay generic type arguments vào descriptor cơ bản.

Ví dụ:

~~~java
// Mã minh họa khai báo:
static long evaluate(byte flag, String[][] names, int[] offsets)
~~~

~~~text
byte         -> B
String[][]   -> [[Ljava/lang/String;
int[]        -> [I
long         -> J

Method descriptor:
(B[[Ljava/lang/String;[I)J
~~~

**Chuỗi parser đọc từ trái sang phải:** Sau dấu **(** là **B** (tham số 1), **[[Ljava/lang/String;** (tham số 2), **[I** (tham số 3); dấu **)** đóng danh sách; **J** là return type.

## 14. Các lỗi phổ biến

### 14.1. Dùng dấu chấm trong object descriptor

**Sai:** **Ljava.lang.String;**.

**Đúng:** **Ljava/lang/String;**.

Object descriptor trong class file dùng internal name, không dùng binary name có dấu chấm.

### 14.2. Dùng tên canonical của nested class khi API cần binary name

**Sai ở ngữ cảnh binary name:** **com.example.Outer.Inner**.

**Đúng:** **com.example.Outer$Inner** khi **Inner** là member class của **Outer**.

Nhưng nhớ rằng **$** cũng là ký tự Java identifier có thể xuất hiện ở nơi khác; không nên suy diễn cấu trúc nested class chỉ bằng thao tác string thiếu metadata.

### 14.3. Thiếu chữ L hoặc dấu ; ở object descriptor

**Sai:** **java/lang/String**, khi vị trí được yêu cầu là *field descriptor*.

**Đúng:** **Ljava/lang/String;**.

Bản thân **java/lang/String** có thể hoàn toàn đúng khi API đang yêu cầu *internal class name*; chỉ sai vì **không khớp loại dữ liệu đầu vào**.

### 14.4. Viết descriptor method với dấu phẩy hoặc kiểu đọc được

**Sai:** **(int,String[])boolean** hoặc **(I,[Ljava/lang/String;)Z**.

**Đúng:** **(I[Ljava/lang/String;)Z**.

Method descriptor không chứa dấu phẩy phân cách tham số.

### 14.5. Nhầm long và object reference

**Sai:** dùng **L** cho kiểu **long**.

**Đúng:** **J** cho **long**; **L<internal-name>;** cho reference class/interface.

### 14.6. Dùng V cho field hoặc phần tử mảng

**Sai:** **V** làm field descriptor hoặc **[V** cho mảng void.

**Đúng:** **V** chỉ dùng làm return descriptor của method trả **void**, ví dụ **()V**.

### 14.7. Quên chiều của mảng

**int[]** là **[I**; **int[][]** là **[[I**. Thiếu một dấu **[** làm thay đổi kiểu hoàn toàn. Một method trả **String[][]** phải kết thúc bằng **[[Ljava/lang/String;**, không phải **[Ljava/lang/String;**.

### 14.8. Đọc getName() của mảng như descriptor trong class file

**String[].class.getName()** → **[Ljava.lang.String;**, còn field descriptor → **[Ljava/lang/String;**. Hai chuỗi không bằng nhau từng ký tự. Với primitive array, sự giống nhau về chuỗi không chứng minh quy tắc áp dụng tương tự cho reference array.

### 14.9. Nhầm descriptor với generic signature

**List<String>** có field descriptor **Ljava/util/List;**; biểu diễn **String** generic không nằm trong descriptor chính. Reflection generic metadata hay **Signature** không phải nơi lấy descriptor thay thế cho code generation.

### 14.10. Nhầm method descriptor với toàn bộ symbolic reference

**java/lang/String.length:()I** chứa owner, method name và descriptor. Phần method descriptor thực sự chỉ là **()I**.

## 15. Bài tập tự kiểm tra

**Câu 1.** Binary name, internal name và field descriptor của **java.util.Map.Entry** là gì?

**Đáp án:**

~~~text
Binary name:    java.util.Map$Entry
Internal name:  java/util/Map$Entry
Descriptor:     Ljava/util/Map$Entry;
~~~

**Câu 2.** Descriptor của **boolean[][][]** và **long[]**?

**Đáp án:** **[[[Z** và **[J**. **boolean** dùng **Z**, **long** dùng **J**.

**Câu 3.** Phân tích **([Ljava/lang/String;I)V**.

**Đáp án:** Method nhận hai tham số **String[]** rồi **int**, trả **void**. Dấu **;** kết thúc descriptor của String component; dấu **I** tiếp theo là tham số thứ hai.

**Câu 4.** **(ILjava/lang/Object;)[[D** nghĩa là gì?

**Đáp án:** Method nhận **int** và **Object**, trả **double[][]**. Đầu ra là mảng hai chiều kiểu double.

**Câu 5.** Field **java.util.List<String> list** có descriptor gì?

**Đáp án:** **Ljava/util/List;**. Thông tin generic String chỉ nằm ở metadata generic khi có, không phải field descriptor.

**Câu 6.** Tại sao **Class.forName("[Ljava.lang.String;")** đúng trong ngữ cảnh Reflection mà **[Ljava/lang/String;** là dạng class-file array descriptor?

**Đáp án:** Reflection **Class.forName** sử dụng array-name encoding với **binary name có dấu chấm** cho reference component, còn class file descriptor dùng **internal name với /**.

**Câu 7.** Một phương thức instance **String read(int n)** có descriptor **(Lmy/pkg/Reader;I)Ljava/lang/String;** để bao gồm **this** không?

**Đáp án:** Không. Descriptor của phương thức là **(I)Ljava/lang/String;**. **this** được truyền ngầm tại runtime, không nằm trong descriptor.

**Câu 8.** Bạn thấy trong **javap -v** một entry **CONSTANT_Class** tham chiếu chuỗi **[I**. Nó sai vì không chứa đường dẫn package hay không?

**Đáp án:** Không. **CONSTANT_Class** có thể mô tả array class bằng **array descriptor**; **[I** là array type int[].

**Câu 9.** Tại sao **(I)V** không thể được hiểu là field descriptor?

**Đáp án:** Ngoặc đơn và return **V** thuộc ngữ pháp **method descriptor**. Field descriptor chỉ mô tả một kiểu, không chứa danh sách tham số hay void return.

## 16. Checklist khi xử lý class file, Reflection và bytecode tooling

1. Xác định API đang đòi **binary name**, **internal name**, **field descriptor**, **method descriptor**, hay **generic signature**.
2. Với nested member class, lấy đúng **binary name** có **$** trước khi chuyển package dots thành **/**.
3. Với primitive, dùng mã một ký tự; với object dùng **L...;**; với array thêm đúng số dấu **[**.
4. Với method, ghép **(parameter descriptors) + return descriptor**, kể cả **V** nếu trả void; không đưa tên và **this** vào.
5. Với array reflection, phân biệt **Class.getName()** (reference component có dấu **.**) với class-file descriptor (dấu **/**).
6. Đừng coi generic Signature là descriptor thường, hoặc coi tên class trong constant pool luôn ở dạng không có **[**.
7. Đọc output **javap -s -p -v** và so sánh với source declaration, method descriptor, constant pool; khi có thể dùng **MethodType** và API typed để tạo chuỗi chính xác.

### Tài liệu chuẩn

- **JVMS Java SE 17, §4.2 — Names**, đặc biệt §4.2.1 Binary Class and Interface Names: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.2
- **JVMS Java SE 17, §4.3.2 — Field Descriptors**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.2
- **JVMS Java SE 17, §4.3.3 — Method Descriptors**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3
- **JVMS Java SE 17, §4.4 — Constant Pool**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4
- **JLS Java SE 17, §13.1 — The Form of a Binary**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1
- **Java 17 API, Class**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java 17 API, MethodType**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html

**Ghi nhớ:** **Binary name** dùng dấu chấm cho package và dấu **$** cho member class; **internal name** dùng **/** thay package dots; **field descriptor** mã hóa một kiểu với **B/C/D/F/I/J/S/Z**, **L...;** hoặc **[...]**; **method descriptor** ghép **(tham số)kiểu trả về**. Với **array class**, cách **Class.getName()** biểu diễn tên tham chiếu dùng dấu chấm và không giống hệt descriptor trong class file. Đọc đúng các ranh giới này giúp bạn tránh phần lớn lỗi khi phân tích class file và làm việc với Reflection/bytecode.
