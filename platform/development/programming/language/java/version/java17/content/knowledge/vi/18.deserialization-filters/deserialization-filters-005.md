# Filter theo pattern và filter viết bằng mã trong Java 17

Java Serialization có thể tái tạo một đồ thị object từ dữ liệu nhị phân bằng ObjectInputStream. Nếu dữ liệu đến từ nguồn không đáng tin cậy, việc chỉ gọi readObject() có thể khiến chương trình tạo ra những kiểu object ngoài dự kiến hoặc xử lý một đồ thị quá lớn, quá sâu. Serialization filtering cho phép giới hạn các class được phép giải tuần tự hóa và giới hạn tài nguyên mà đồ thị object có thể sử dụng.

Java 17 hỗ trợ hai cách xây dựng filter chính:

- **Filter theo pattern**: mô tả class được phép/từ chối và các giới hạn bằng một chuỗi cấu hình.
- **Filter viết bằng mã**: triển khai ObjectInputFilter để kiểm tra từng đối tượng, mảng và thông tin về đồ thị khi dữ liệu được đọc.

Hai cách có thể được dùng ở cấp ObjectInputStream hoặc trong chính sách toàn JVM. Java 17 còn có cơ chế filter factory để chọn filter theo ngữ cảnh. Bài này tập trung vào cú pháp pattern, cách viết filter bằng code và cách gắn chúng vào quá trình giải tuần tự hóa.

## 1. Vì sao cần serialization filter?

Khi đọc dữ liệu Java Serialization, chương trình không chỉ đọc một chuỗi byte đơn giản. Stream có thể mô tả:

- class của từng object;
- các trường và giá trị của object;
- mảng và độ dài mảng;
- tham chiếu giữa các object;
- quan hệ lồng nhau tạo thành một đồ thị object.

Nếu ứng dụng đọc stream không đáng tin cậy mà không có chính sách lọc, dữ liệu có thể yêu cầu tạo object không mong muốn, tạo mảng quá lớn hoặc tạo đồ thị có độ sâu và số lượng tham chiếu vượt quá khả năng xử lý của ứng dụng.

Serialization filter cho phép ứng dụng kiểm tra thông tin về object **trong lúc giải tuần tự hóa**, trước khi chấp nhận object đó. Filter có thể:

1. cho phép một class cụ thể hoặc một nhóm class;
2. từ chối class không nằm trong chính sách;
3. giới hạn độ sâu đồ thị;
4. giới hạn số tham chiếu, số byte đã đọc và độ dài mảng.

API chuẩn là java.io.ObjectInputFilter, được giới thiệu từ Java 9 theo JEP 290 và tiếp tục được hỗ trợ trong Java 17.

**Filter là một lớp bảo vệ cho Java Serialization.** Nếu giao thức không cần Java native serialization, nên cân nhắc định dạng dữ liệu có schema rõ ràng như JSON, Protocol Buffers hoặc một định dạng phù hợp khác. Nếu vẫn phải đọc object serialization, cần áp dụng filter và kiểm tra dữ liệu nghiệp vụ sau khi đọc.

## 2. ObjectInputFilter hoạt động như thế nào?

ObjectInputFilter được gọi khi ObjectInputStream đang đọc các thành phần của đồ thị object. Filter nhận một FilterInfo chứa thông tin về phần tử đang được xử lý và trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| ALLOWED | Filter này cho phép phần tử hiện tại. |
| REJECTED | Filter từ chối phần tử; quá trình đọc sẽ thất bại. |
| UNDECIDED | Filter không đưa ra quyết định cho phần tử hiện tại. |

Các thông tin chính mà FilterInfo cung cấp:

| Phương thức | Thông tin |
| --- | --- |
| serialClass() | Class của object hoặc mảng đang được giải tuần tự hóa; có thể null với một số lần gọi như tham chiếu quay lại object đã đọc. |
| arrayLength() | Độ dài mảng nếu phần tử đang xét là mảng; trả về giá trị âm nếu không phải mảng. |
| depth() | Độ sâu hiện tại của đồ thị object. |
| references() | Số tham chiếu đã được xử lý trong stream. |
| streamBytes() | Số byte đã được đọc từ stream tại thời điểm kiểm tra. |

Một filter có thể chỉ kiểm tra class, chỉ kiểm tra giới hạn tài nguyên hoặc kết hợp cả hai.

### 2.1. Ba trạng thái không có cùng ý nghĩa

Không được nhầm UNDECIDED với REJECTED:

- ALLOWED nghĩa là filter này có quyết định cho phép.
- REJECTED nghĩa là filter này có quyết định từ chối.
- UNDECIDED nghĩa là filter không áp dụng quy tắc nào cho trường hợp đó.

Nếu filter không có pattern khớp, filter theo pattern trả về UNDECIDED. Điều đó **không tự động biến thành từ chối**. Khi không có filter khác đưa ra quyết định từ chối, ObjectInputStream có thể tiếp tục đọc object.

Vì vậy, nếu muốn xây dựng allowlist (chỉ cho phép một nhóm class), phải có quy tắc từ chối mặc định cho các class còn lại. Với pattern, thường dùng !** ở cuối. Với filter bằng code, trả về REJECTED cho class không nằm trong allowlist.

## 3. Cú pháp filter theo pattern

Java cung cấp ObjectInputFilter.Config.createFilter(String pattern) để tạo filter từ chuỗi cấu hình.

Một pattern có thể gồm:

- tên class chính xác;
- tên package với wildcard;
- tên module kết hợp tên class hoặc package;
- quy tắc từ chối bắt đầu bằng dấu !;
- các giới hạn maxdepth, maxrefs, maxbytes và maxarray.

Các phần tử được phân cách bằng dấu chấm phẩy. Pattern được xét theo thứ tự từ trái sang phải; pattern class đầu tiên khớp sẽ quyết định ALLOWED hoặc REJECTED. Các giới hạn tài nguyên được kiểm tra độc lập với quy tắc class và nếu vượt giới hạn thì filter từ chối.

### 3.1. Khớp một class cụ thể

Tên class được viết bằng tên đầy đủ (fully qualified class name):

~~~text
com.acme.model.Order
~~~

Pattern này khớp class com.acme.model.Order. Nó không tự động khớp các class khác trong cùng package.

### 3.2. Khớp package

Hai wildcard package thường dùng:

| Pattern | Phạm vi |
| --- | --- |
| com.acme.model.* | Các class trực tiếp trong package com.acme.model. |
| com.acme.model.** | Các class trong com.acme.model và các package con của nó. |

Ví dụ:

~~~text
com.acme.model.*
~~~

khớp com.acme.model.Order nhưng không khớp com.acme.model.internal.OrderRecord.

Trong khi đó:

~~~text
com.acme.model.**
~~~

khớp cả class trong package gốc và các package con.

Hãy chọn wildcard hẹp nhất đáp ứng nhu cầu. Cho phép toàn bộ package lớn có thể vô tình cho phép class nội bộ hoặc class không cần thiết.

### 3.3. Khớp theo module

Pattern có thể chỉ rõ module bằng cách đặt tên module trước dấu gạch chéo:

~~~text
java.base/java.lang.String
java.base/java.util.ArrayList
~~~

Pattern thứ nhất chỉ rõ class String thuộc module java.base. Pattern thứ hai chỉ rõ ArrayList trong cùng module.

Có thể kết hợp module với package wildcard:

~~~text
java.base/java.util.*
~~~

Pattern này khớp các class trực tiếp trong package java.util của module java.base.

Nếu không ghi module, pattern class/package được áp dụng theo tên class/package mà không giới hạn vào một module cụ thể.

### 3.4. Wildcard toàn cục và dấu từ chối

Hai wildcard đặc biệt:

| Pattern | Ý nghĩa |
| --- | --- |
| * | Tất cả class trong unnamed module. |
| ** | Tất cả class trong mọi module. |

Thêm dấu ! ở đầu để từ chối:

~~~text
!com.acme.model.internal.**
!**
~~~

Pattern đầu từ chối package nội bộ và các package con. Pattern thứ hai từ chối mọi class trong mọi module.

Ví dụ một allowlist có thể cho phép một số class trước, rồi từ chối phần còn lại:

~~~text
com.acme.model.**;java.base/java.lang.String;!**
~~~

Trong ví dụ, class thuộc package model và String được cho phép; class khác bị từ chối bởi quy tắc cuối. Khi viết allowlist, thứ tự rất quan trọng: nếu đặt !** lên trước các pattern cho phép, các pattern sau không còn cơ hội quyết định đối với class đã bị khớp.

## 4. Các giới hạn tài nguyên trong pattern

Pattern hỗ trợ bốn giới hạn:

| Giới hạn | Ý nghĩa |
| --- | --- |
| maxdepth | Độ sâu tối đa của đồ thị object. |
| maxrefs | Số tham chiếu tối đa được xử lý. |
| maxbytes | Số byte tối đa được đọc từ stream. |
| maxarray | Độ dài tối đa của một mảng. |

Ví dụ:

~~~text
maxdepth=20;maxrefs=10000;maxbytes=5000000;maxarray=100000
~~~

Đây là các ngưỡng minh họa. Giá trị phù hợp phải dựa trên kích thước dữ liệu hợp lệ của ứng dụng, không nên sao chép máy móc.

### 4.1. maxdepth

Giới hạn độ sâu đồ thị object. Nếu một object tham chiếu đến object khác, object đó lại tham chiếu tiếp, độ sâu có thể tăng dần.

~~~text
Order
 └── Customer
      └── Address
           └── ...
~~~

Giới hạn độ sâu giúp ngăn đồ thị lồng nhau quá sâu, có thể gây tiêu thụ tài nguyên lớn hoặc làm tăng rủi ro stack/resource exhaustion.

### 4.2. maxrefs

Giới hạn số tham chiếu đã được xử lý. Đây không đơn giản là số lượng class khác nhau. Đồ thị có nhiều object và nhiều liên kết có thể làm số tham chiếu tăng nhanh.

### 4.3. maxbytes

Giới hạn số byte đã đọc từ ObjectInputStream. Nó giúp giới hạn kích thước dữ liệu đầu vào mà quá trình giải tuần tự hóa chấp nhận.

maxbytes không thay thế giới hạn kích thước request ở tầng mạng hoặc giới hạn kích thước file trước khi mở. Ứng dụng vẫn nên giới hạn input ở nơi tiếp nhận dữ liệu.

### 4.4. maxarray

Giới hạn độ dài mảng. Một mảng có thể yêu cầu cấp phát vùng nhớ lớn dù số lượng object khác trong stream không nhiều.

Nếu dữ liệu hợp lệ có mảng lớn, chọn ngưỡng đủ dùng nhưng vẫn có giới hạn rõ ràng. Filter bằng code cũng có thể kiểm tra arrayLength() trực tiếp.

## 5. Ví dụ tạo filter theo pattern

Giả sử ứng dụng chỉ cần đọc các DTO thuộc package com.acme.model và String, đồng thời giới hạn kích thước đồ thị:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;" +
        "maxrefs=10000;" +
        "maxbytes=5000000;" +
        "maxarray=100000;" +
        "com.acme.model.**;" +
        "java.base/java.lang.String;" +
        "!**"
);
~~~

Ý nghĩa:

1. Không cho đồ thị vượt quá độ sâu 20.
2. Không cho số tham chiếu vượt quá 10.000.
3. Không cho stream đọc quá 5.000.000 byte.
4. Không cho mảng dài hơn 100.000 phần tử.
5. Cho phép class trong package model và package con.
6. Cho phép String trong module java.base.
7. Từ chối các class còn lại.

Gắn filter vào ObjectInputStream trước khi gọi readObject():

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

static Object readFiltered(InputStream source)
        throws IOException, ClassNotFoundException {
    ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
            "maxdepth=20;maxrefs=10000;maxbytes=5000000;" +
            "maxarray=100000;com.acme.model.**;" +
            "java.base/java.lang.String;!**"
    );

    try (ObjectInputStream input = new ObjectInputStream(source)) {
        input.setObjectInputFilter(filter);
        return input.readObject();
    }
}
~~~

Đặt filter trước lần đọc object đầu tiên. Nếu filter từ chối một class hoặc giới hạn bị vượt, thao tác giải tuần tự hóa thất bại; ứng dụng cần xử lý IOException/InvalidClassException phù hợp.

**Lưu ý về allowlist thực tế:** một DTO có thể chứa collection, mảng hoặc các class phụ trợ khác. Filter phải cho phép đúng các kiểu thực sự có trong đồ thị hợp lệ. Không nên mở rộng wildcard thành toàn bộ java.util hoặc toàn bộ java.base chỉ để làm cho một ví dụ chạy được; hãy xác định dependency serialization cụ thể.

## 6. Cấu hình filter theo pattern ở cấp JVM

Có thể cấu hình một filter chung khi khởi chạy JVM bằng system property jdk.serialFilter:

~~~bash
java -Djdk.serialFilter="maxdepth=20;maxrefs=10000;maxbytes=5000000;maxarray=100000;com.acme.model.**;java.base/java.lang.String;!**" -jar app.jar
~~~

Chính sách cấp JVM có thể bảo vệ nhiều ObjectInputStream trong tiến trình. Đây là lựa chọn hữu ích cho môi trường triển khai muốn áp dụng baseline chung, kể cả khi một số thành phần không tự cấu hình filter.

Các điểm cần lưu ý:

- Cấu hình filter toàn JVM ảnh hưởng tới nhiều luồng deserialization trong tiến trình; cần kiểm tra tương thích với thư viện và dữ liệu hợp lệ.
- Pattern allowlist hẹp có thể làm các thư viện khác không đọc được class mà chúng cần.
- Không nên để cấu hình toàn cục quá rộng chỉ để tránh lỗi tương thích.
- Nên cấu hình từ lúc khởi chạy và quản lý cùng cấu hình bảo mật của ứng dụng.

JDK cũng hỗ trợ cấu hình qua security property theo quy tắc của runtime. Cách triển khai cần được quản lý tập trung, tránh để mỗi thành phần tự đặt một chính sách mâu thuẫn.

## 7. Filter viết bằng mã với ObjectInputFilter

Khi pattern không đủ linh hoạt, có thể viết filter bằng lambda hoặc class riêng. Đây là cách phù hợp khi cần:

- kiểm tra class bằng Class<?> và logic Java;
- xử lý riêng array component type;
- kết hợp nhiều giới hạn theo ngữ cảnh;
- đọc thông tin FilterInfo để áp dụng quy tắc tùy biến;
- tạo allowlist rõ ràng bằng tập class.

Một filter được khai báo dưới dạng:

~~~java
ObjectInputFilter filter = info -> {
    // Kiểm tra thông tin và trả về Status.
};
~~~

### 7.1. Kiểm tra giới hạn trước khi xét class

Ví dụ filter chỉ chấp nhận class OrderSnapshot và String:

~~~java
import java.io.ObjectInputFilter;

final class OrderSnapshot implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final String status;
    private final long createdAtEpochMillis;

    OrderSnapshot(String orderId, String status, long createdAtEpochMillis) {
        this.orderId = orderId;
        this.status = status;
        this.createdAtEpochMillis = createdAtEpochMillis;
    }
}

static ObjectInputFilter orderFilter() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 1000
                || info.streamBytes() > 1_000_000
                || info.arrayLength() > 10_000) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (type == OrderSnapshot.class || type == String.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
~~~

Filter này thực hiện hai bước:

1. Từ chối ngay nếu một giới hạn tài nguyên bị vượt.
2. Chỉ cho phép đúng hai class đã liệt kê; class khác bị từ chối.

serialClass() có thể null, chẳng hạn khi filter được gọi cho tham chiếu tới object đã đọc. Trường hợp này không có class mới để kiểm tra; trả UNDECIDED giúp filter không gán nhầm một class.

Ví dụ trên cố ý dùng DTO đơn giản với String và kiểu primitive. Nếu DTO có các field object khác, phải bổ sung chính xác các class đó vào allowlist.

### 7.2. Kiểm tra mảng theo component type

Khi DTO có mảng, chỉ kiểm tra arrayLength() chưa đủ. Cần xác định loại phần tử của mảng:

~~~java
static ObjectInputFilter arrayAwareFilter() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 5000
                || info.streamBytes() > 2_000_000) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (type.isArray()) {
            if (info.arrayLength() > 50_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> component = type.getComponentType();
            if (component.isPrimitive() || component == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        }

        if (type == OrderSnapshot.class || type == String.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
~~~

Ở đây:

- Mảng có độ dài vượt 50.000 bị từ chối.
- Mảng primitive được cho phép.
- Mảng String được cho phép.
- Mảng object có component type khác bị từ chối.
- Class không nằm trong allowlist bị từ chối.

Nếu ứng dụng cần mảng LineItem[], hãy thêm LineItem.class vào điều kiện component type. Không cho phép Object[] một cách rộng rãi nếu chưa có lý do, vì đó là kiểu chứa được nhiều loại object; các object phần tử vẫn phải được filter riêng, nhưng allowlist càng cụ thể càng dễ kiểm soát.

## 8. Gắn filter vào ObjectInputStream

Có thể gắn filter bằng setObjectInputFilter():

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

static Object deserialize(InputStream source)
        throws IOException, ClassNotFoundException {
    try (ObjectInputStream input = new ObjectInputStream(source)) {
        input.setObjectInputFilter(orderFilter());
        return input.readObject();
    }
}
~~~

Gắn filter trước khi đọc object. Trong thiết kế thông thường, filter của stream được thiết lập một lần ở giai đoạn khởi tạo và không thay đổi tùy tiện sau khi đã bắt đầu đọc dữ liệu.

Nếu filter trả REJECTED, ObjectInputStream ném lỗi giải tuần tự hóa, thường được biểu diễn bằng InvalidClassException. Ứng dụng nên bắt lỗi ở ranh giới tiếp nhận dữ liệu, ghi log đủ để chẩn đoán nhưng tránh ghi payload nhạy cảm vào log.

### 8.1. Kiểm tra kiểu kết quả sau khi đọc

Filter kiểm soát class và tài nguyên, nhưng vẫn cần kiểm tra kiểu object ở biên API:

~~~java
Object value = deserialize(source);
if (!(value instanceof OrderSnapshot order)) {
    throw new IOException("Dữ liệu không phải OrderSnapshot");
}
~~~

Sau đó, kiểm tra các quy tắc nghiệp vụ như orderId có hợp lệ không, status có thuộc tập trạng thái cho phép không và timestamp có nằm trong miền hợp lý không.

Không nên coi việc filter cho phép class là bằng chứng rằng object có dữ liệu nghiệp vụ hợp lệ.

## 9. Pattern và filter bằng code: chọn cách nào?

| Tiêu chí | Filter theo pattern | Filter viết bằng mã |
| --- | --- | --- |
| Khai báo | Chuỗi cấu hình. | Lambda hoặc class triển khai ObjectInputFilter. |
| Allowlist class | Tên class/package/module. | So sánh Class<?> hoặc tập class. |
| Giới hạn tài nguyên | maxdepth, maxrefs, maxbytes, maxarray. | Đọc FilterInfo và tự kiểm tra. |
| Logic phức tạp | Hạn chế. | Linh hoạt hơn. |
| Dễ cấu hình lúc triển khai | Tốt, có thể dùng jdk.serialFilter. | Cần code hoặc filter factory. |
| Kiểm soát array component | Hạn chế theo pattern. | Có thể dùng Class.isArray() và getComponentType(). |
| Phù hợp | Chính sách allow/deny và giới hạn tiêu chuẩn. | Quy tắc theo ngữ cảnh hoặc kiểm tra class phức tạp. |

Không cần chọn duy nhất một cách cho mọi nơi. Pattern phù hợp cho baseline đơn giản, dễ quản lý. Filter bằng code phù hợp khi ứng dụng cần allowlist theo kiểu dữ liệu hoặc điều kiện động.

## 10. Kết hợp filter và filter factory trong Java 17

Một ứng dụng có thể có nhiều nguồn chính sách:

- filter toàn JVM do quản trị viên cấu hình;
- filter riêng cho một ObjectInputStream;
- filter theo loại dữ liệu hoặc ngữ cảnh request.

Nếu các chính sách được kết hợp không nhất quán, một filter ít nghiêm ngặt hơn có thể vô tình làm suy yếu chính sách khác. Java 17 bổ sung cơ chế **context-specific deserialization filters** theo JEP 415, thông qua filter factory.

Filter factory là một BinaryOperator<ObjectInputFilter> được dùng để chọn filter cho ObjectInputStream. Factory được gọi khi stream được tạo và khi ứng dụng thiết lập filter riêng cho stream. Factory nhận filter hiện tại và filter được yêu cầu, rồi trả về filter cuối cùng sẽ dùng.

API cấu hình nằm trong ObjectInputFilter.Config:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory((current, requested) -> {
    // Chọn hoặc kết hợp chính sách theo ngữ cảnh.
    return requested;
});
~~~

Đoạn trên chỉ minh họa vị trí tích hợp của factory, không phải chính sách hoàn chỉnh để dùng production: trả thẳng requested có thể không giữ lại chính sách hiện tại. Khi triển khai thực tế, factory phải xác định cách kết hợp filter toàn JVM, filter của stream và chính sách theo ngữ cảnh; quy tắc phải bảo đảm filter từ chối nghiêm ngặt hơn không bị bỏ qua.

Có thể cấu hình factory qua system property jdk.serialFilterFactory theo cơ chế của Java 17. Factory là điểm mở rộng cấp tiến trình, nên cần được thiết lập sớm và quản lý thống nhất; không để từng thư viện tự thay factory toàn cục.

### 10.1. Khi nào cần filter factory?

Filter factory hữu ích khi cùng một JVM giải tuần tự hóa nhiều loại dữ liệu khác nhau:

- request loại A chỉ được chứa DTO A;
- dữ liệu cache loại B có một allowlist khác;
- thành phần quản trị có chính sách riêng;
- ứng dụng cần bảo đảm mọi stream vẫn tuân theo baseline toàn cục.

Với ứng dụng nhỏ chỉ có một loại dữ liệu, filter riêng trên từng ObjectInputStream thường dễ hiểu và đủ dùng. Không cần thêm factory nếu không có nhu cầu quản lý chính sách nhiều ngữ cảnh.

## 11. Lỗi thường gặp khi viết filter

### 11.1. Chỉ đặt giới hạn nhưng không tạo allowlist

Pattern:

~~~text
maxdepth=20;maxrefs=10000;maxbytes=5000000
~~~

chỉ đặt giới hạn tài nguyên. Class không bị giới hạn có thể trả về UNDECIDED và vẫn được đọc nếu không có filter khác từ chối.

Nếu cần allowlist, thêm các class được phép và quy tắc từ chối mặc định:

~~~text
maxdepth=20;com.acme.model.**;!**
~~~

### 11.2. Đặt !** ở đầu

Pattern:

~~~text
!**;com.acme.model.**
~~~

đã từ chối mọi class trước khi đến quy tắc cho phép. Đặt allowlist trước, deny-all sau:

~~~text
com.acme.model.**;!**
~~~

### 11.3. Nhầm * với **

- * chỉ khớp class trong unnamed module.
- ** khớp class trong mọi module.

Nếu mục tiêu là từ chối mọi class không được liệt kê, !** thường phù hợp hơn !*.

### 11.4. Dùng package wildcard quá rộng

Pattern:

~~~text
com.acme.**
~~~

có thể cho phép nhiều class hơn dự kiến, gồm package nội bộ, class phục vụ framework hoặc class không thuộc DTO công khai. Hãy dùng package con cụ thể và deny các vùng nhạy cảm nếu cần.

### 11.5. Trả UNDECIDED cho class không biết

Trong filter viết bằng code, nếu mục tiêu là allowlist, nhánh mặc định nên trả REJECTED:

~~~java
if (isAllowed(type)) {
    return ObjectInputFilter.Status.ALLOWED;
}
return ObjectInputFilter.Status.REJECTED;
~~~

Trả UNDECIDED cho mọi class lạ sẽ khiến filter không thực sự chặn các class đó.

### 11.6. Bỏ qua mảng

Một class được cho phép có thể chứa mảng rất lớn hoặc mảng có kiểu phần tử không mong muốn. Hãy kiểm tra arrayLength() và component type khi dữ liệu hợp lệ có mảng.

### 11.7. Chỉ filter class mà quên giới hạn tài nguyên

Allowlist class không tự giới hạn số lượng object, độ sâu graph hoặc kích thước mảng. Hãy đặt các ngưỡng tài nguyên phù hợp cùng với quy tắc class.

### 11.8. Cho rằng filter thay thế xác thực dữ liệu

Filter chỉ quyết định class và các chỉ số tài nguyên trong quá trình đọc. Nó không kiểm tra người gửi có quyền gửi dữ liệu đó hay không, dữ liệu có chữ ký hợp lệ không hoặc trạng thái nghiệp vụ có hợp lệ không. Các kiểm tra đó vẫn cần ở tầng ứng dụng.

## 12. Ví dụ hoàn chỉnh: đọc OrderSnapshot bằng allowlist

Ví dụ sau sử dụng filter viết bằng code và một DTO đơn giản:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class FilteredDeserializationDemo {
    static final class OrderSnapshot implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String orderId;
        private final String status;

        OrderSnapshot(String orderId, String status) {
            this.orderId = orderId;
            this.status = status;
        }

        @Override
        public String toString() {
            return "OrderSnapshot[orderId=" + orderId
                    + ", status=" + status + "]";
        }
    }

    static ObjectInputFilter filter() {
        return info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 100_000
                    || info.arrayLength() > 1_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == OrderSnapshot.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        OrderSnapshot original =
                new OrderSnapshot("ORD-1001", "CONFIRMED");

        byte[] serialized;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(original);
            output.flush();
            serialized = bytes.toByteArray();
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(serialized))) {
            input.setObjectInputFilter(filter());

            Object value = input.readObject();
            if (!(value instanceof OrderSnapshot order)) {
                throw new InvalidClassException(
                        "Unexpected root object type");
            }

            System.out.println(order);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac FilteredDeserializationDemo.java
java FilteredDeserializationDemo
~~~

Ví dụ dùng dữ liệu do chính chương trình tạo để minh họa API. Trong ứng dụng thật, nguồn byte có thể đến từ file, network hoặc cache; không nên xem dữ liệu tự tạo trong demo là mô hình đủ an toàn cho đầu vào bên ngoài.

## 13. Quy trình thiết kế filter cho ứng dụng

Khi xây dựng chính sách lọc, có thể làm theo trình tự:

1. Liệt kê các class thực sự cần có trong object graph hợp lệ.
2. Xác định package/module chứa các class đó.
3. Chọn pattern hẹp hoặc allowlist bằng code.
4. Đặt maxdepth, maxrefs, maxbytes và maxarray dựa trên dữ liệu hợp lệ lớn nhất cùng biên an toàn.
5. Gắn filter trước lần readObject đầu tiên.
6. Kiểm thử cả payload hợp lệ và payload phải bị từ chối.
7. Kiểm tra xử lý exception và log khi filter từ chối.
8. Nếu có nhiều ngữ cảnh deserialization trong cùng JVM, cân nhắc filter factory và quy tắc kết hợp chính sách.
9. Sau khi đọc, kiểm tra kiểu root object và validate các trường nghiệp vụ.

Không nên đặt giới hạn quá nhỏ khiến dữ liệu hợp lệ bị từ chối, cũng không nên đặt ngưỡng cực lớn chỉ để tránh lỗi. Cần đo kích thước object graph thực tế và ghi rõ lý do của từng ngưỡng.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Object lạ vẫn được đọc | Pattern không khớp nên filter trả UNDECIDED. | Thêm deny-all như !** hoặc trả REJECTED cho class ngoài allowlist. |
| Class hợp lệ bị từ chối | Allowlist thiếu class phụ thuộc trong graph. | Xem class thực tế cần thiết và thêm chính xác class đó. |
| Pattern cho phép quá nhiều class | Dùng wildcard package quá rộng. | Thu hẹp package hoặc chỉ rõ class/module. |
| Filter không chặn đồ thị quá lớn | Chỉ kiểm tra class, chưa đặt giới hạn tài nguyên. | Thêm maxdepth, maxrefs, maxbytes và maxarray hoặc kiểm tra FilterInfo trong code. |
| Mảng lớn vẫn được tạo | Không kiểm tra giới hạn array length. | Đặt maxarray và kiểm tra arrayLength() trong filter code. |
| Class trong package con không khớp | Dùng package.* thay vì package.**. | Chọn wildcard theo phạm vi package cần thiết. |
| Class trong named module không bị !* từ chối | !* chỉ áp dụng class thuộc unnamed module. | Dùng !** nếu cần từ chối class trong mọi module. |
| Stream ném InvalidClassException | Filter trả REJECTED hoặc class không tương thích. | Xác định filter status và class bị từ chối; không bỏ filter chỉ để đọc được dữ liệu. |
| Filter toàn JVM làm thư viện cũ lỗi | Chính sách global quá hẹp hoặc không tính tới graph hợp lệ của thư viện. | Xác định dependency serialization và thiết kế policy rõ ràng; không nới rộng mù quáng. |
| Filter factory làm mất policy hiện tại | Factory thay filter cũ bằng filter mới mà không kết hợp chính sách. | Thiết kế quy tắc kết hợp bảo toàn các quyết định REJECTED nghiêm ngặt. |
| Object được filter cho phép nhưng dữ liệu vẫn sai | Filter không kiểm tra quy tắc nghiệp vụ. | Validate object sau khi đọc và kiểm tra quyền ở tầng ứng dụng. |

## 15. Bài tập tự luyện

### Bài 1 — Đọc pattern

Giải thích ý nghĩa của pattern:

~~~text
maxdepth=15;maxrefs=5000;com.acme.dto.**;java.base/java.lang.String;!**
~~~

Cho biết class trong package com.acme.dto.internal có được cho phép không và class không thuộc các package đã nêu sẽ nhận quyết định nào.

### Bài 2 — Sửa thứ tự pattern

Pattern sau có vấn đề gì?

~~~text
!**;com.acme.dto.**
~~~

Hãy sắp xếp lại để cho phép package DTO trước và từ chối class còn lại sau.

### Bài 3 — Viết allowlist bằng code

Viết một ObjectInputFilter chỉ cho phép hai class CustomerSnapshot và String. Từ chối mọi class khác. Thêm giới hạn depth tối đa 12, references tối đa 500 và streamBytes tối đa 200.000.

### Bài 4 — Kiểm tra mảng

Viết filter cho phép mảng byte[] tối đa 1 MB và mảng String[] tối đa 100 phần tử. Từ chối các loại mảng khác. Gợi ý: kiểm tra type.isArray(), type.getComponentType() và info.arrayLength().

### Bài 5 — Phân biệt UNDECIDED và REJECTED

Một filter trả UNDECIDED khi gặp class không nằm trong allowlist. Giải thích vì sao đây chưa phải default-deny và sửa nhánh mặc định để từ chối class không biết.

### Bài 6 — Chọn nơi cấu hình

Một ứng dụng có ba thành phần đọc các loại serialized object khác nhau. Hãy đề xuất cách kết hợp filter toàn JVM, filter riêng cho từng stream và filter factory trong Java 17. Giải thích cách bảo đảm một chính sách từ chối không bị filter ít nghiêm ngặt hơn ghi đè.

## 16. Ghi nhớ khi dùng serialization filter

- ObjectInputFilter kiểm soát class và giới hạn tài nguyên trong lúc ObjectInputStream giải tuần tự hóa.
- Pattern được tạo bằng ObjectInputFilter.Config.createFilter và các mục phân cách bằng dấu chấm phẩy.
- Tên class khớp chính xác; package.* chỉ khớp package trực tiếp; package.** bao gồm các package con.
- Pattern module/class có thể giới hạn class theo module; * khớp class trong unnamed module, ** khớp class trong mọi module.
- Dấu ! dùng để từ chối; thứ tự pattern class rất quan trọng, nên đặt allowlist trước deny-all.
- maxdepth, maxrefs, maxbytes và maxarray giới hạn độ sâu graph, số tham chiếu, byte đã đọc và độ dài mảng.
- UNDECIDED không đồng nghĩa REJECTED; muốn default-deny phải từ chối class ngoài allowlist.
- Filter viết bằng code có thể dùng FilterInfo để kiểm tra class, array length, depth, references và stream bytes.
- Gắn filter vào ObjectInputStream trước khi đọc object; xử lý lỗi khi filter từ chối.
- Java 17 có filter factory theo JEP 415 để chọn filter theo ngữ cảnh; cần kết hợp chính sách một cách nhất quán.
- Filter không thay thế xác thực nguồn gửi, kiểm tra quyền hoặc validation dữ liệu nghiệp vụ sau khi đọc.
- Chỉ tiếp tục dùng Java native serialization khi có lý do rõ ràng; với dữ liệu không đáng tin cậy, filter là lớp phòng vệ quan trọng nhưng không phải biện pháp duy nhất.

### Tài liệu tham khảo

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) — FilterInfo, Status, filter pattern và các giới hạn.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html) — tạo filter theo pattern, cấu hình filter và filter factory.
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html) — gắn filter cho stream giải tuần tự hóa.
- [JEP 290: Filter Incoming Serialization Data](https://openjdk.org/jeps/290) — serialization filtering và các giới hạn đồ thị.
- [JEP 415: Context-Specific Deserialization Filters](https://openjdk.org/jeps/415) — filter factory và chính sách theo ngữ cảnh trong Java 17.
