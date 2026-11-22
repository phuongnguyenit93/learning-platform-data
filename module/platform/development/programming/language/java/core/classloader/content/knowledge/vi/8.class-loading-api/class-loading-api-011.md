# Điều khiển assertion theo lớp, package và giá trị mặc định

## 1. Assertion trong Java được bật hoặc tắt ở đâu?

Java có câu lệnh **assert** dùng để kiểm tra giả định nội bộ của chương trình:

~~~java
assert balance >= 0;
assert result != null : "Unexpected null result";
~~~

Khi assertion **được bật** cho class chứa câu lệnh, biểu thức điều kiện được đánh giá. Nếu điều kiện là false, JVM ném **AssertionError**; biểu thức thông báo sau dấu hai chấm, nếu có, được đánh giá khi cần tạo lỗi. Khi assertion **bị tắt**, toàn bộ câu lệnh assert không đánh giá những biểu thức này. Do đó, **không đặt side effect hoặc nghiệp vụ bắt buộc trong assert**.

Assertion thường bị tắt theo mặc định ở các class ứng dụng khi chạy lệnh `java` không cấu hình. Người chạy chương trình có thể bật/tắt chúng bằng tùy chọn **-ea/-da**, còn code điều khiển class loader có thể đặt chính sách bằng các API **ClassLoader.setDefaultAssertionStatus**, **setPackageAssertionStatus** và **setClassAssertionStatus**.

Bài học này giải thích ba cấp chính sách: **mặc định của loader, theo package và theo class**, quy tắc ưu tiên, thời điểm có hiệu lực, thao tác xóa chính sách, giới hạn với nested class và tương tác với tùy chọn JVM. Trọng tâm là class loader và cách chính sách ảnh hưởng những class **sẽ được khởi tạo**.

## 2. Bộ bốn API trên `java.lang.ClassLoader`

| API | Ý nghĩa | Phạm vi tác động |
| --- | --- | --- |
| **setDefaultAssertionStatus(boolean enabled)** | Đặt mặc định bật/tắt assertion cho loader. | Các class được loader quản lý và khởi tạo về sau, trừ trường hợp có override theo package/class. |
| **setPackageAssertionStatus(String packageName, boolean enabled)** | Đặt mặc định của package. | Package được nêu và mọi **subpackage** của nó, nếu không có chính sách cụ thể hơn. |
| **setClassAssertionStatus(String className, boolean enabled)** | Đặt chính sách theo một **top-level class**. | Top-level class được nêu cùng những nested class bên trong nó. |
| **clearAssertionStatus()** | Xóa các chỉ thị theo class/package và đặt mặc định của loader thành **false**. | Các class được khởi tạo về sau trong phạm vi loader. |

Cả bốn đều là phương thức **public** của ClassLoader, nên có thể gọi trên object loader khi có quyền truy cập tham chiếu đó:

~~~java
ClassLoader loader = MyApplication.class.getClassLoader();
loader.setDefaultAssertionStatus(true);
loader.setPackageAssertionStatus("com.example.service", false);
loader.setClassAssertionStatus("com.example.service.Checker", true);
~~~

Đoạn trên là code minh họa đặt vào một ứng dụng có class MyApplication và Checker; chưa phải một chương trình tự chạy độc lập. Phần sau có ví dụ hoàn chỉnh.

**Boolean có nghĩa trực tiếp:** true = bật assertion, false = tắt assertion. Không có tham số tên class dạng **`Class<?>`** trong những phương thức này: class được chỉ định bằng **chuỗi tên**. Đừng lẫn giá trị này với **Class.desiredAssertionStatus()**, vốn là API đọc trạng thái mong muốn.

## 3. Thứ tự ưu tiên: class > package cụ thể nhất > mặc định

Nếu một class có nhiều quy tắc phù hợp, sử dụng thứ tự sau:

1. **Quy tắc cho top-level class** nếu được chỉ định, có ưu tiên cao nhất, kể cả với nested class thuộc top-level đó.
2. **Quy tắc package cụ thể nhất** áp dụng cho class, tức package có tên dài nhất trong cây package áp dụng.
3. **Mặc định của chính class loader**, nếu không có override phù hợp.

~~~text
Cần quyết định assertion status của class C
                    |
                    v
    Có chỉ thị cho top-level class chứa C?
            |                     |
           Có                   Không
            |                     |
            v                     v
    Dùng class status      Có package status?
                                  |       |
                                 Có      Không
                                  |       |
                                  v       v
                        Chọn package   Dùng mặc định
                        cụ thể nhất    của loader
~~~

Ví dụ loader có chính sách:

~~~java
loader.setDefaultAssertionStatus(true);
loader.setPackageAssertionStatus("app", false);
loader.setPackageAssertionStatus("app.data", true);
loader.setClassAssertionStatus("app.data.Special", false);
~~~

Kết quả đối với những class khởi tạo sau khi thiết lập chính sách:

| Class | Chính sách được chọn | Assertion |
| --- | --- | --- |
| **other.Task** | Default của loader | Bật |
| **app.Main** | Package app | Tắt |
| **app.web.Controller** | Package app (bao gồm subpackage) | Tắt |
| **app.data.Repository** | Package app.data cụ thể hơn app | Bật |
| **app.data.deep.Parser** | Package app.data | Bật |
| **app.data.Special** | Class override | Tắt |
| **app.data.Special.Nested** | Chính sách top-level Special | Tắt |

Lưu ý tên trong bảng mô tả class theo cú pháp Java; binary name của nested class thông thường dùng ký tự **$**, nhưng API **setClassAssertionStatus** nhận **tên top-level class** khi muốn điều khiển cả lớp và nested classes của nó.

### 3.1 Package và subpackage được xác định bằng dấu chấm

Nếu đặt chính sách cho **app.data**, nó áp dụng cho chính **app.data** và các package bắt đầu bằng **app.data.**, chẳng hạn **app.data.deep**. Nó **không** áp dụng cho **app.database** vì tên này không bắt đầu bằng **app.data.**.

Java không có quan hệ kế thừa package trong ngôn ngữ: “subpackage” ở đây là cách API assertion dùng **tiền tố tên package** để chọn mặc định. Quy tắc package cụ thể hơn luôn thắng package cha, dù quy tắc cha được gọi trước hay sau.

### 3.2 Package không tên (unnamed package)

Có thể dùng:

~~~java
loader.setPackageAssertionStatus(null, true);
~~~

Giá trị **null** đại diện cho **unnamed package** hiện hành. Không dùng chuỗi rỗng thay cho null khi theo hợp đồng API. Ở code thực tế, nên tổ chức các class vào named package; nhưng tính năng này giúp kiểm soát ứng dụng hoặc ví dụ Java không khai báo package.

## 4. `setClassAssertionStatus` nhận tên top-level class

Đây là một chi tiết dễ bỏ sót trong Javadoc.

~~~java
loader.setClassAssertionStatus("com.example.Outer", true);
~~~

Thao tác này đặt chính sách cho top-level class **Outer** và các nested class trong Outer, như **Outer.Inner** hoặc **Outer.StaticNested**. Với nested class, giá trị mong muốn được lấy theo top-level enclosing class theo quy tắc assertion.

Ngược lại, dùng tên của nested class để gọi API:

~~~java
loader.setClassAssertionStatus("com.example.Outer$Inner", false);
~~~

**Không thay đổi assertion status thực tế của nested class** theo hợp đồng API. Tham số ở đây được thiết kế cho **top-level class**; nếu muốn điều khiển một nested class riêng biệt bằng string tên đó, phương thức này không cung cấp quyền chọn như vậy.

**Đừng nhầm với `ClassLoader.loadClass`:** loadClass thường nhận **binary name** của class đang tải, kể cả dấu **$** với nested class. Nhưng **setClassAssertionStatus** áp dụng chính sách assertion ở cấp **top-level** và nested classes bên trong.

Trong cùng một top-level class, nếu muốn có kiểm tra chỉ bật ở một số nơi, có thể tổ chức logic qua các top-level class riêng, hoặc sử dụng cơ chế kiểm soát/kiểm thử khác phù hợp; không lạm dụng chính sách assertion để điều khiển nghiệp vụ.

## 5. Thời điểm đặt chính sách: trước khi class được khởi tạo

Theo ClassLoader API, các setter ảnh hưởng tới **những class sẽ được khởi tạo trong tương lai**. Một class đã khởi tạo thì **không đổi trạng thái thực thi assertion** chỉ vì loader được cấu hình lại.

~~~text
Thời điểm A: loader.setClassAssertionStatus("app.Task", true)
                    |
                    v
Thời điểm B: app.Task initialized lần đầu
             → assertion status của Task được chốt
                    |
                    v
Thời điểm C: loader.setClassAssertionStatus("app.Task", false)
             → không tắt assertion đã được chốt cho Task
~~~

Bốn tình huống cần phân biệt:

- **Chỉ có đối tượng Class** (ví dụ lấy từ **Class.forName(name, false, loader)**) chưa đồng nghĩa class đã initialized.
- **Đã load/link nhưng chưa initialized:** thiết lập assertion status vẫn có thể ảnh hưởng lúc class được khởi tạo, theo hợp đồng API.
- **Đã initialized:** thay đổi cấu hình loader không đổi cách thực thi các assert đã được quyết định cho class đó.
- **Một class khác chưa initialized:** cấu hình mới có thể áp dụng cho class khác ấy ngay cả khi cùng package.

Vì vậy, nếu chương trình muốn điều khiển assertion của một nhóm class, nên đặt chính sách **trước khi có active use** của chúng (ví dụ trước khi new instance, gọi static method hoặc đọc static field không phải compile-time constant).

### 5.1 Assertion status không phải biến được đọc ở mỗi câu lệnh

Compiler có thể tạo trường tổng hợp như **$assertionsDisabled** trong bytecode class, với trạng thái dựa trên chính sách assertion khi class initialized. Một lần thay đổi loader về sau không khiến mọi assert trong class đã init tự đọc lại cấu hình.

Có thể quan sát bytecode bằng:

~~~bash
javap -c -p lab.rules.PackageProbe
~~~

Tùy compiler và class, output có thể có trường tổng hợp liên quan đến assertion; tên và bố cục là chi tiết biên dịch, không nên dùng làm public API.

## 6. Ví dụ chạy được số 1: cấp default, package, subpackage, class và clear

Ví dụ Java 17+ dưới đây kiểm tra toàn bộ thứ tự ưu tiên bằng những class chưa được khởi tạo. Mỗi **enabled()** cố ý dùng **assert false** và bắt AssertionError để xác định việc assert có được thực thi hay không. Đó là **test probe**, không phải khuyến nghị viết assertion kiểu này trong production.

Cấu trúc thư mục:

~~~text
project/
└── src/
    └── lab/
        ├── rules/
        │   ├── PolicyDemo.java
        │   └── deep/
        │       └── DeepProbe.java
        └── misc/
            └── DefaultProbe.java
~~~

**src/lab/rules/PolicyDemo.java**:

~~~java
package lab.rules;

import lab.misc.DefaultProbe;
import lab.rules.deep.DeepProbe;

public class PolicyDemo {
    public static void main(String[] args) {
        ClassLoader loader = PolicyDemo.class.getClassLoader();

        loader.clearAssertionStatus();
        loader.setDefaultAssertionStatus(true);
        loader.setPackageAssertionStatus("lab.rules", false);
        loader.setPackageAssertionStatus("lab.rules.deep", true);
        loader.setClassAssertionStatus("lab.rules.ClassProbe", true);

        System.out.println("package = " + PackageProbe.enabled());
        System.out.println("class = " + ClassProbe.enabled());
        System.out.println("nested = " + ClassProbe.Nested.enabled());
        System.out.println("subpackage = " + DeepProbe.enabled());
        System.out.println("default = " + DefaultProbe.enabled());

        loader.setPackageAssertionStatus("lab.rules", true);
        System.out.println("late package = " + LateProbe.enabled());

        loader.clearAssertionStatus();
        System.out.println("initialized class = " + ClassProbe.enabled());
        System.out.println("future class = " + FutureProbe.enabled());
    }
}

class PackageProbe {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}

class ClassProbe {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }

    static class Nested {
        static boolean enabled() {
            try {
                assert false : "probe";
                return false;
            } catch (AssertionError expected) {
                return true;
            }
        }
    }
}

class LateProbe {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}

class FutureProbe {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}
~~~

**src/lab/misc/DefaultProbe.java**:

~~~java
package lab.misc;

public class DefaultProbe {
    public static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}
~~~

**src/lab/rules/deep/DeepProbe.java**:

~~~java
package lab.rules.deep;

public class DeepProbe {
    public static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}
~~~

Đứng ở thư mục **project**, biên dịch và chạy:

~~~bash
javac -d out src/lab/rules/PolicyDemo.java src/lab/misc/DefaultProbe.java src/lab/rules/deep/DeepProbe.java
java -cp out lab.rules.PolicyDemo
~~~

Stdout đã được kiểm chứng trên JDK 21 (code dùng các API sẵn có từ Java 17):

~~~text
package = false
class = true
nested = true
subpackage = true
default = true
late package = true
initialized class = true
future class = false
~~~

### 6.1 Phân tích tám kết quả

**package = false:** **PackageProbe** ở package **lab.rules**. Quy tắc package false ưu tiên cao hơn default true.

**class = true:** **ClassProbe** cũng thuộc **lab.rules**, nhưng có override class true. Quy tắc class thắng package false.

**nested = true:** **ClassProbe.Nested** nằm bên trong top-level ClassProbe, nên kế thừa chính sách assert dành cho ClassProbe, dù có package rule false.

**subpackage = true:** **DeepProbe** thuộc **lab.rules.deep**. Quy tắc package cụ thể nhất **lab.rules.deep = true** thắng **lab.rules = false**.

**default = true:** **DefaultProbe** thuộc **lab.misc**, không có rule package/class riêng, nên dùng default true.

**late package = true:** Sau khi thay **lab.rules** thành true, **LateProbe** chưa initialized nhận chính sách mới.

**initialized class = true:** Trước đó ClassProbe đã initialized ở dòng 2. Lệnh **clearAssertionStatus()** không tắt assert đã được chốt trong ClassProbe.

**future class = false:** FutureProbe đến lúc này mới initialized. **clearAssertionStatus()** đã xóa các override và reset default về false, nên FutureProbe có assertion disabled.

### 6.2 Vì sao ví dụ chủ động gọi `clearAssertionStatus` ngay đầu?

Để kết quả độc lập với cấu hình assertion mà JVM hoặc người chạy đã truyền cho application loader, chương trình dọn trạng thái loader trước khi đặt các rule. **clearAssertionStatus** không mang nghĩa “trả về các thiết lập ban đầu từ dòng lệnh”; nó **đặt default=false và xóa tất cả override theo package/class trên loader này**. Nếu cần khôi phục một policy cụ thể, phải thiết lập lại các rule tương ứng bằng API.

Không áp dụng kỹ thuật reset assertion status một cách tùy tiện lên application loader trong sản phẩm lớn: nhiều thư viện có thể đã khởi tạo class hoặc phụ thuộc vào cấu hình assertion của môi trường. Ví dụ chỉ minh họa ý nghĩa API trong chương trình cô lập.

## 7. Điều khiển assertion bằng JVM options

Trước khi JVM khởi chạy ứng dụng, người chạy có thể truyền các tùy chọn:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| **-ea** hoặc **-enableassertions** | Bật assertion mặc định cho class ứng dụng thích hợp. |
| **-da** hoặc **-disableassertions** | Tắt assertion mặc định. |
| **-ea:com.example...** | Bật assertion trong package com.example và subpackages. |
| **-da:com.example.internal...** | Tắt assertion trong package internal và các subpackages. |
| **-ea:com.example.Service** | Bật assertion cho top-level class được nêu (và nested classes của nó). |
| **-da:com.example.Service** | Tắt assertion cho class được nêu. |
| **-ea:...** | Bật assertion trong unnamed package. |
| **-esa** hoặc **-enablesystemassertions** | Bật assertion trong system classes. |
| **-dsa** hoặc **-disablesystemassertions** | Tắt assertion trong system classes. |

Các option có thể kết hợp; JVM xử lý các tùy chọn theo thứ tự trên command line trước khi loading những class liên quan. Trường hợp **-ea** không đối số có một ngoại lệ đối với system classes: dùng **-esa/-dsa** khi muốn điều khiển riêng những class hệ thống.

### 7.1 Ví dụ chạy được số 2: class option khác package option

Tạo file **src/lab/flags/FlagsDemo.java**:

~~~java
package lab.flags;

public class FlagsDemo {
    static class Nested {
        static boolean enabled() {
            try {
                assert false : "probe";
                return false;
            } catch (AssertionError expected) {
                return true;
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("nested = " + Nested.enabled());
        System.out.println("peer = " + Peer.enabled());
    }
}

class Peer {
    static boolean enabled() {
        try {
            assert false : "probe";
            return false;
        } catch (AssertionError expected) {
            return true;
        }
    }
}
~~~

Từ thư mục project:

~~~bash
javac -d out src/lab/flags/FlagsDemo.java
java -ea:lab.flags.FlagsDemo -cp out lab.flags.FlagsDemo
~~~

Stdout:

~~~text
nested = true
peer = false
~~~

Giải thích: option **-ea:lab.flags.FlagsDemo** bật assertion cho top-level class FlagsDemo và nested class **FlagsDemo.Nested**, nhưng **Peer** là top-level class khác trong cùng package nên vẫn theo mặc định (false).

Lệnh khác:

~~~bash
java -ea:lab.flags... -da:lab.flags.Peer -cp out lab.flags.FlagsDemo
~~~

Stdout:

~~~text
nested = true
peer = false
~~~

Ở đây package **lab.flags** được bật trước, nhưng option riêng cho class **Peer** được tắt. Kết quả tương tự, nhưng **nguồn quyết định** đã khác.

Nếu chỉ chạy:

~~~bash
java -ea:lab.flags... -cp out lab.flags.FlagsDemo
~~~

kết quả sẽ là:

~~~text
nested = true
peer = true
~~~

Vì cả FlagsDemo.Nested và Peer đều nằm trong package được bật.

### 7.2 So sánh dòng lệnh và API của ClassLoader

| Phương diện | Tùy chọn `java -ea/-da` | Phương thức ClassLoader |
| --- | --- | --- |
| Ai cấu hình? | Người chạy JVM / script chạy ứng dụng | Code đang có tham chiếu loader |
| Thời điểm điển hình | Trước khi chương trình chạy | Trước lúc những class tương ứng khởi tạo |
| Phạm vi | Có thể hướng đến nhiều loader theo option JVM | Áp dụng chính sách trên object loader được gọi |
| Cấp class/package/default | Có các lựa chọn tương ứng | Có ba setter cụ thể |
| Xóa toàn bộ override? | Đặt lại option lúc khởi động | **clearAssertionStatus()** trên loader |
| Tác động tới class đã initialized? | Không thể đổi bằng CLI trong cùng lần chạy | Setter sau đó cũng không đổi trạng thái đã chốt |

Các API ClassLoader cho phép một loader chủ động thay đổi thiết lập assertion liên quan đến loader ấy, kể cả bỏ qua cấu hình từ command line khi gọi clearAssertionStatus. Trong ứng dụng thực tế, cần kiểm tra loader **thực sự định nghĩa** class để tránh đặt chính sách lên child loader trong khi parent mới là nơi cung cấp Class.

## 8. ClassLoader nào phải nhận cấu hình?

Một ứng dụng có thể có bootstrap loader, platform loader, application loader, và nhiều loader cho plugin. Mỗi class thông thường có một **defining loader**; các loader khác có thể delegate để nhận cùng đối tượng Class.

Nếu gọi:

~~~java
pluginLoader.setPackageAssertionStatus("shared.api", true);
~~~

nhưng **shared.api** được parent loader định nghĩa thông qua delegation, không thể mặc nhiên kết luận rule trên pluginLoader sẽ điều khiển assertion của class do parent định nghĩa. Cấu hình phải tương ứng với **loader quản lý việc định nghĩa và chính sách assertion của class đó**.

Khi gỡ lỗi:

~~~java
Class<?> type = loader.loadClass("com.example.Service");
System.out.println(type.getClassLoader());
~~~

`type.getClassLoader()` cho biết **defining loader** của class (hoặc null nếu bootstrap). Lời gọi **loader.loadClass(name)** có thể trả về Class do loader khác định nghĩa. Muốn áp dụng rule chính xác, cần hiểu delegation và nơi lớp sẽ được initialized.

**Ví dụ dễ nhầm:** plugin loader child-first đối với package nội bộ, nhưng parent-first đối với các API chung. Chính sách assertion riêng ở plugin loader có thể phù hợp với implementation class của plugin; những class API từ parent phải theo policy của parent.

## 9. Thời điểm assertion khác với thời điểm lập trình viên gọi setter

Giả sử:

~~~java
Class<?> metadata = Class.forName("lab.rules.LateProbe", false, loader);
loader.setPackageAssertionStatus("lab.rules", true);
~~~

Nếu LateProbe **chưa initialized**, việc thay policy có thể ảnh hưởng khi nó được sử dụng lần đầu. **Class.forName(name, false, loader)** theo API lấy Class mà không chủ động initialize. Ngược lại:

~~~java
Class<?> metadata = Class.forName("lab.rules.LateProbe", true, loader);
loader.setPackageAssertionStatus("lab.rules", true);
~~~

Với initialize=true, LateProbe đã được yêu cầu khởi tạo trước khi setter chạy; nếu initialization thành công, đổi policy sau đó không thay assertion status đã chốt.

Hai đoạn là **minh họa ý nghĩa API**, không phải chương trình độc lập: cần có sẵn loader và class phù hợp. Ngoài ra JVM có thể đã khởi tạo class đó từ một active use khác trước khi gặp đoạn code. Không nên xem `Class.forName(..., false, ...)` như cách quay ngược trạng thái một class đã initialized.

## 10. `Class.desiredAssertionStatus()` dùng thế nào?

API:

~~~java
boolean desired = SomeClass.class.desiredAssertionStatus();
~~~

trả về trạng thái assertion **mong muốn** cho class theo cấu hình phù hợp. Từ “desired” rất quan trọng: nó giúp xem cấu hình ở góc độ Class API, nhưng không nên sử dụng thao tác gọi lại sau khi cấu hình thay đổi để kết luận rằng một class **đã initialized** sẽ đổi trạng thái thực thi các lệnh assert.

Để kiểm tra hành vi thực sự của một câu lệnh assert, hãy quan sát chính class chứa nó (như method **enabled()** trong ví dụ), hoặc dùng test cô lập với class chưa khởi tạo. Không dựa riêng trên tên package, tên loader hoặc giá trị một Boolean cấu hình để phán đoán mã đã initialized.

Nếu assert mang biểu thức có side effect, trạng thái enabled/disabled sẽ làm hành vi chương trình khác nhau, đây chính là lý do tránh dùng assert cho validation bắt buộc.

## 11. Khi nào nên dùng assertion, khi nào không?

Assertion thích hợp cho **invariant nội bộ** mà lập trình viên tin rằng phải đúng nếu code triển khai đúng, ví dụ:

~~~java
assert index >= 0 && index < buffer.length;
assert state != null : "Internal state must exist";
~~~

Với dữ liệu đầu vào từ người dùng, validation bắt buộc hoặc điều kiện an toàn của hệ thống, **không dùng assert làm cơ chế duy nhất**:

~~~java
// Validation bắt buộc, chạy cả khi assertions bị tắt:
if (amount < 0) {
    throw new IllegalArgumentException("amount must be >= 0");
}
~~~

Trong production, assertions có thể bị tắt theo mặc định hoặc được cấu hình chọn lọc. Một chương trình đúng phải tiếp tục thực hiện các thao tác cần thiết bất kể policy assertion.

Tránh:

~~~java
// SAI: khi assertions disabled, counter++ sẽ không chạy.
assert counter++ >= 0;
~~~

Ưu tiên tính toán tách biệt:

~~~java
counter++;
assert counter >= 0;
~~~

Hai đoạn cuối là snippet minh họa đặt trong method có biến counter phù hợp.

## 12. Những nhầm lẫn phổ biến

### 12.1 “Đặt default=true có thể bật lại tất cả class đã khởi tạo”

Không. Setter áp dụng cho những class **sẽ được initialized**; class đã initialized có trạng thái assertion cố định. Muốn test chính sách mới, hãy dùng class mới chưa initialized hoặc chạy lại JVM với cấu hình khác.

### 12.2 “Đặt package=false là đủ dù class đã được bật riêng”

Không. Class-specific override thắng package, kể cả package cụ thể nhất. Nếu cần thay đổi chính sách cho class chưa initialized, phải chỉnh chính rule class (hoặc xóa trạng thái trên loader rồi cấu hình lại, hiểu rõ hậu quả với class khác).

### 12.3 “Quy tắc package cha luôn ưu tiên hơn package con”

Sai. Package có tên **cụ thể nhất** thắng. Ví dụ **app.data=true** thắng **app=false** cho **app.data.deep.Model**, trừ khi có rule class cụ thể.

### 12.4 “Có thể set `Outer$Inner` để chỉ bật nested class”

Theo hợp đồng **setClassAssertionStatus**, lời gọi chỉ áp dụng cho tên **top-level class** và nested classes trong đó. Dùng tên không phải top-level không thay đổi trạng thái thực tế của class được nhắm. Dùng tên **Outer** để kiểm soát cả nhóm.

### 12.5 “clearAssertionStatus khôi phục mọi cài đặt từ lệnh java”

Không. Phương thức đặt default của loader thành **false** và xóa các rule package/class của loader. Nó không phải cơ chế hoàn nguyên giá trị trước đó.

### 12.6 “Đã có `Class` nghĩa là assertion status đã chốt”

Không nhất thiết. **Loading** và **initialization** là hai giai đoạn khác nhau; status được quyết định theo quy tắc initialization của class. Cẩn thận nếu một thao tác reflection hoặc active use khác đã khởi tạo class trước.

### 12.7 “Set rule trên child loader chắc chắn tác động class parent”

Không thể khẳng định. Delegation có thể trả Class do parent định nghĩa. Kiểm tra **getClassLoader()**, cách loader phân phối định nghĩa, và thời điểm class khởi tạo.

### 12.8 “AssertionError nên bị catch để chương trình chạy tiếp trong production”

Trong ví dụ, bắt AssertionError chỉ để **quan sát trạng thái assertion một cách quyết định**. Trong code ứng dụng, AssertionError thường biểu thị giả định nội bộ bị phá vỡ, nên cần điều tra sửa logic thay vì nuốt lỗi.

## 13. Quy trình kiểm tra khi assertion không chạy

1. Xác nhận code thực sự chứa **assert** và execution path đi qua câu lệnh đó.
2. Xác định class chứa assert đã **initialized** chưa; setter sau thời điểm đó sẽ không đổi hành vi.
3. Kiểm tra có option JVM **-ea/-da/-esa/-dsa** hay không.
4. Với loader được dùng, xem **default**, package rule cụ thể nhất và class rule.
5. Nếu class nested, xác định đúng **top-level class** chi phối policy.
6. Kiểm tra **defining loader** bằng **Class.getClassLoader()**, nhất là với plugin/classloader delegation.
7. Nếu dùng **clearAssertionStatus()**, nhớ nó đã reset default=false và xóa các override.
8. Viết test nhỏ chạy trong JVM mới để tránh class đã initialized và so sánh kết quả.

Đặc biệt, không kết luận class “chưa loaded” chỉ vì một assert không chạy: assert có thể đơn giản đã bị disable.

## 14. Bài tập tự kiểm tra

**Câu 1.** Default của loader là true; package **shop** được đặt false; class **shop.Cart** được đặt true. Assertion trong Cart bật hay tắt nếu Cart chưa initialized?

**Đáp án:** Bật. Rule theo class ưu tiên cao hơn package.

**Câu 2.** Default false; package **shop=true**, package **shop.internal=false**. Class **shop.internal.engine.Parser** dùng rule nào?

**Đáp án:** **shop.internal=false**, vì đây là package cụ thể nhất phù hợp.

**Câu 3.** Nếu class đã initialized với assertion disabled, gọi **setClassAssertionStatus(className, true)** có bật assert của class đó không?

**Đáp án:** Không; trạng thái thực thi của class đã initialized không thay đổi.

**Câu 4.** Muốn bật assertion trong top-level **sample.Outer** và nested **Outer.Nested**, gọi API nào?

**Đáp án:** **setClassAssertionStatus("sample.Outer", true)** trước initialization. Không dùng chuỗi **sample.Outer$Nested** để điều khiển riêng nested class.

**Câu 5.** **clearAssertionStatus()** có khôi phục trạng thái từ option **-ea** không?

**Đáp án:** Không; nó xóa rule package/class và đặt default=false trên loader.

**Câu 6.** Câu **assert x++ > 0;** gây lỗi logic gì khi assertion tắt?

**Đáp án:** Biểu thức không được đánh giá, nên **x++ không chạy**. Assertion không nên chứa side effect bắt buộc.

**Câu 7.** Vì sao **-ea:lab.flags.FlagsDemo** bật nested class nhưng không bật class ngang hàng **Peer**?

**Đáp án:** Option nhắm tới top-level FlagsDemo và nested classes thuộc nó; Peer là top-level class độc lập.

**Câu 8.** Đã set package rule trên pluginLoader nhưng class thực tế do parent định nghĩa. Cần kiểm tra gì?

**Đáp án:** Xem **Class.getClassLoader()**, delegation và nơi policy của defining loader được quản lý; không mặc nhiên áp dụng rule trên child cho class của parent.

## 15. Tổng kết

Ba cấp kiểm soát assertion của ClassLoader được áp dụng theo nguyên tắc:

~~~text
       class-specific rule
               ↓ thắng
       package-specific rule
       (package sâu nhất)
               ↓ thắng
       default rule của loader
~~~

- **setDefaultAssertionStatus** đặt giá trị mặc định.
- **setPackageAssertionStatus** áp dụng cho một package và các subpackages; package cụ thể hơn thắng.
- **setClassAssertionStatus** áp dụng cho top-level class và nested classes của nó; class rule thắng các rule khác.
- **clearAssertionStatus** xóa rule và đặt default về false.
- Các chỉnh sửa chính sách ảnh hưởng tới class **sẽ initialized**, không đảo ngược trạng thái class đã initialized.
- JVM options **-ea/-da** cho phép kiểm soát ngay lúc chạy; ứng dụng còn có thể chủ động đặt policy trên loader.
- Assertion dùng để kiểm tra giả định nội bộ, **không thay validation bắt buộc** và không nên có side effect.

### Tài liệu tham khảo

- **ClassLoader, Java SE 21** – bốn phương thức điều khiển assertion và quy tắc ưu tiên: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- **The java Command, Java 17** – tùy chọn -ea, -da, -esa, -dsa: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **JLS §14.10 (The assert Statement), Java SE 21** – quy tắc thực thi assert: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.10
- **JLS §12.4 (Initialization), Java SE 21** – thời điểm khởi tạo class và interface: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4
