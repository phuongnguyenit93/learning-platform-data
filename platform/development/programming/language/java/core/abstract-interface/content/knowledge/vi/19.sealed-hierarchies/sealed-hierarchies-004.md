# Yêu cầu cùng module hoặc cùng package trong unnamed module

## Mục tiêu

Bài này giải thích ranh giới vị trí mà Java áp dụng cho các kiểu được `permits` trong một sealed hierarchy: khi sealed type thuộc **named module**, các kiểu con được phép phải thuộc cùng module; khi nó thuộc **unnamed module**, các kiểu con được phép phải nằm trong cùng package. Bạn sẽ biết cách khai báo `sealed`, `permits`, chọn `final`/ `sealed`/ `non-sealed` cho lớp con và nhận ra những lỗi biên dịch thường gặp.

## 1. Sealed type kiểm tra gì khi biên dịch?

~~~java
public sealed interface Shape permits Circle, Rectangle {}
~~~

`permits` chỉ liệt kê các kiểu con **trực tiếp**. `Circle` và `Rectangle` phải thực sự `implements Shape` và cùng đáp ứng chính sách nhánh: class khai báo `final`, `sealed` hoặc `non-sealed`; record là `final` ngầm định. Interface con chỉ dùng `sealed` hoặc `non-sealed`.

Enum cũng có thể trực tiếp triển khai sealed interface. Enum **không có** hằng với thân lớp riêng là `final` ngầm định; enum **có** hằng với thân lớp riêng là `sealed` ngầm định. Enum không thể `extends` một sealed class tùy ý. Vị trí của các kiểu con được phép là quy tắc tiếp theo cần kiểm tra.

## 2. Named module: các kiểu được phép phải cùng module

Một **named module** là module được khai báo bằng tệp `module-info.java`. Nếu sealed type nằm trong named module, tất cả các kiểu con trực tiếp được liệt kê trong `permits` phải thuộc cùng named module đó. Chúng **có thể nằm ở các package khác nhau** trong module.

Ví dụ cấu trúc:

~~~text
src/
└── com.example.shapes/
    ├── module-info.java
    ├── com/example/api/Shape.java
    └── com/example/impl/Circle.java
~~~

`module-info.java`:

~~~java
module com.example.shapes {
    exports com.example.api;
}
~~~

`com/example/api/Shape.java`:

~~~java
package com.example.api;

public sealed interface Shape permits com.example.impl.Circle {
}
~~~

`com/example/impl/Circle.java`:

~~~java
package com.example.impl;

public final class Circle implements com.example.api.Shape {
}
~~~

Trong ví dụ, `Shape` và `Circle` ở hai package khác nhau nhưng cùng thuộc module `com.example.shapes`, vì cả hai được biên dịch và đóng gói trong cùng module. Đây là cách hợp lệ theo quy tắc vị trí của sealed hierarchy. Ví dụ minh họa cấu trúc module; để chạy thực tế, hãy biên dịch module theo cấu trúc thư mục module-source-path hoặc công cụ build của dự án.

Nếu chuyển `Circle` sang một named module khác, khai báo `permits com.example.impl.Circle` sẽ không hợp lệ dù tên kiểu được viết đúng và kiểu đó trực tiếp triển khai `Shape`. Ranh giới bắt buộc là module, không phải chỉ là việc package có cùng tên.

## 3. Unnamed module: các kiểu được phép phải cùng package

Nếu sealed type được nạp trong **unnamed module** (trường hợp thường gặp khi chạy ứng dụng từ classpath mà không có khai báo module), tất cả các kiểu con trực tiếp được phép phải ở **cùng package** với sealed type.

Ví dụ này chạy trên classpath và dùng package `demo` cho tất cả các kiểu:

`src/demo/Transport.java`

~~~java
package demo;

public sealed interface Transport permits Car, Bike {
}
~~~

`src/demo/Car.java`

~~~java
package demo;

public final class Car implements Transport {
}
~~~

`src/demo/Bike.java`

~~~java
package demo;

public final class Bike implements Transport {
}
~~~

`src/demo/SealedDemo.java`

~~~java
package demo;

public class SealedDemo {
    public static void main(String[] args) {
        Transport transport = new Car();
        System.out.println(transport instanceof Car ? "car" : "other");
    }
}
~~~

Biên dịch từ thư mục gốc chứa `src`:

~~~text
javac -d out src/demo/Transport.java src/demo/Car.java src/demo/Bike.java src/demo/SealedDemo.java
java -cp out demo.SealedDemo
~~~

Kết quả stdout:

~~~text
car
~~~

Không có `module-info.java` nên các lớp trong ví dụ được chạy từ classpath và thuộc unnamed module. Tất cả khai báo `package demo;` vì vậy `Car` và `Bike` cùng package với `Transport`, thỏa quy tắc của unnamed module.

Nếu đổi `Car` thành `package demo.impl;`, chỉ việc đặt tệp trong thư mục con `demo/impl` không đủ để làm nó cùng package với `Transport`. Package được quyết định bởi khai báo `package` và danh tính package trong môi trường biên dịch/nạp lớp, không chỉ bởi vị trí tệp. Khi dùng unnamed module, kiểu con trực tiếp được phép ở package khác sẽ gây lỗi biên dịch.

## 4. Đừng nhầm unnamed module với unnamed package

Hai khái niệm này khác nhau:

- **Unnamed module:** mã không thuộc một named module. Ứng dụng Java truyền thống chạy từ classpath thường nằm trong unnamed module.
- **Unnamed package:** kiểu không có khai báo `package` ở đầu tệp nguồn.

Một unnamed module vẫn có thể chứa nhiều package có tên, chẳng hạn `demo`, `demo.model` và `demo.service`. Với sealed type trong unnamed module, các kiểu con trực tiếp được phép phải ở cùng package cụ thể với kiểu cha; việc cả hai cùng thuộc unnamed module là chưa đủ.

Ngược lại, khi dùng named module, quy tắc vị trí cho phép các kiểu con trực tiếp ở package khác nhau miễn là tất cả nằm trong cùng module. Vì vậy, hãy xác định module trước, rồi áp dụng đúng ranh giới: **cùng module nếu là named module; cùng package nếu là unnamed module**.

## 5. Khi nào cần ghi permits?

Nếu các kiểu con trực tiếp được phép được khai báo cùng compilation unit với sealed type, Java có thể suy ra danh sách permitted subclasses và mệnh đề `permits` có thể được bỏ qua. Nếu các kiểu con được khai báo ở những compilation unit khác, cần khai báo danh sách `permits` rõ ràng.

Ví dụ khai báo trong cùng một tệp nguồn:

~~~java
sealed interface Message {
}

final class TextMessage implements Message {
}

final class BinaryMessage implements Message {
}
~~~

Trong trường hợp này, hai kiểu con được khai báo cùng compilation unit với `Message`, nên danh sách permitted subclasses có thể được suy ra. Dù viết `permits` tường minh hay để compiler suy ra, các quy tắc về module/package và modifier của kiểu con vẫn áp dụng như nhau.

## 6. Lỗi thường gặp và cách chẩn đoán

1. **Cùng module nhưng khác package trong unnamed module:** không hợp lệ. Trong unnamed module, kiểu con trực tiếp phải cùng package với sealed type.
2. **Cùng package name nhưng thuộc module khác:** không hợp lệ với sealed type trong named module. Các kiểu con trực tiếp phải thuộc cùng named module.
3. **Chỉ dựa vào đường dẫn thư mục:** thư mục trông giống nhau không chứng minh package/module hợp lệ. Kiểm tra khai báo `package`, `module-info.java` và cách biên dịch.
4. **Quên khai báo kiểu con trong permits:** khi kiểu con nằm ở compilation unit khác, thêm nó vào mệnh đề `permits` của sealed type.
5. **Kiểu con không trực tiếp kế thừa/triển khai sealed type:** `permits` chỉ liệt kê các kiểu con trực tiếp, không phải cháu/chắt trong cây kế thừa.
6. **Kiểu con không có modifier phù hợp:** lớp con trực tiếp phải là `final`, `sealed` hoặc `non-sealed` (record là final ngầm định).
7. **Hiểu nhầm phạm vi của quy tắc:** ràng buộc cùng package/module nói về các permitted direct subclasses. Nếu một lớp con được phép là `non-sealed`, các lớp kế thừa tiếp từ nó tuân theo quy tắc kế thừa thông thường và không tự động phải ở cùng package/module với sealed ancestor.

Khi gặp lỗi, hãy kiểm tra lần lượt: sealed type có `permits` đúng không; mỗi tên có trỏ tới kiểu con trực tiếp không; kiểu cha và kiểu con thuộc named module hay unnamed module; vị trí package/module có đúng quy tắc không; và modifier của mỗi kiểu con có hợp lệ không.

## 7. Checklist thiết kế

- Xác định sealed type được biên dịch trong named module hay unnamed module.
- Với named module, giữ mọi kiểu con trực tiếp được phép trong cùng module; package có thể khác nhau.
- Với unnamed module, đặt mọi kiểu con trực tiếp được phép trong cùng package với sealed type.
- Khai báo `permits` khi các kiểu con không cùng compilation unit hoặc khi cần thể hiện danh sách được phép rõ ràng.
- Chọn `final`, `sealed` hoặc `non-sealed` cho từng kiểu con theo chính sách mở rộng.
- Biên dịch bằng cấu hình module/classpath thực tế của dự án để phát hiện sai lệch giữa package và module.

## Kết luận

Quy tắc vị trí của sealed hierarchy phụ thuộc vào loại module chứa sealed type. Trong named module, các permitted direct subclasses phải thuộc cùng module nhưng có thể ở package khác nhau. Trong unnamed module, chúng phải nằm cùng package với sealed type. Phân biệt đúng hai trường hợp giúp tổ chức mã sealed rõ ràng và tránh lỗi biên dịch khi chia kiểu ra nhiều tệp hoặc package.