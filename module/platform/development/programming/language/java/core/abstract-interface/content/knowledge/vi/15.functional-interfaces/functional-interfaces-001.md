# Functional interface và hợp đồng hàm duy nhất trong Java

**Functional interface** (interface hàm) là interface có một phương thức trừu tượng chức năng duy nhất theo quy tắc của Java. Hợp đồng này cho biết một hành vi cần nhận tham số gì và tạo kết quả nào; lambda expression hoặc method reference có thể cung cấp phần triển khai cho nó.

## 1. Một hợp đồng được dùng như thế nào?

Ví dụ, hợp đồng cộng hai số nguyên có thể được mô tả bằng interface:

```java
@FunctionalInterface
interface IntOperation {
    int apply(int left, int right);
}

public class FunctionalInterfaceConceptDemo {
    public static void main(String[] args) {
        IntOperation add = (left, right) -> left + right;
        System.out.println(add.apply(3, 4));
    }
}
```

Lưu thành `FunctionalInterfaceConceptDemo.java`, sau đó biên dịch và chạy:

```bash
javac FunctionalInterfaceConceptDemo.java
java FunctionalInterfaceConceptDemo
```

Kết quả:

```text
7
```

Kiểu biến `IntOperation` là **kiểu đích** của lambda. Nhờ chữ ký `apply(int, int)`, compiler biết lambda phải nhận hai số nguyên và trả về một kết quả tương thích với `int`. Lambda cung cấp hành vi cho hợp đồng; nó không tạo thêm phương thức hay thay đổi khai báo interface.

## 2. “Một phương thức” không có nghĩa chỉ có một dòng khai báo

Khi xác định functional interface, Java xét các phương thức abstract được khai báo và kế thừa cùng những quy tắc về chữ ký:

- Các phương thức abstract độc lập như `read()` và `write(String)` tạo ra hai nghĩa vụ khác nhau. Một lambda đơn lẻ không thể triển khai cả hai.
- Những khai báo abstract kế thừa có chữ ký tương đương và kiểu trả về tương thích có thể cùng đại diện cho một hợp đồng chức năng.
- Các phương thức `default`, `static` và `private` có thân không tạo thêm nghĩa vụ abstract.
- Phương thức abstract tương ứng với public instance method của `Object`, như `equals(Object)`, được xử lý theo quy tắc riêng và không tự tạo thêm SAM.
- Một `sealed interface` không thể làm kiểu đích cho lambda, dù chỉ khai báo một phương thức abstract.

Các bài về kế thừa interface, phương thức của `Object`, các loại method và giới hạn của `sealed interface` đi sâu vào từng trường hợp. Điểm cần nhớ ở đây là compiler xác định **một hợp đồng chức năng hợp lệ**, chứ không đếm đơn giản số dòng có từ khóa `abstract`.

Ví dụ sau có hai hợp đồng abstract độc lập nên không phải functional interface:

```java
interface ReadWrite {
    String read();
    void write(String value);
}
```

Interface này vẫn hợp lệ trong Java và có thể được triển khai bằng một lớp cụ thể. Tuy nhiên, không thể dùng một lambda để cung cấp đồng thời cả `read()` và `write(String)`.

## 3. Vai trò của `@FunctionalInterface`

Gắn `@FunctionalInterface` lên interface để yêu cầu compiler kiểm tra ý định thiết kế đó. Annotation là tùy chọn: interface đáp ứng quy tắc Java vẫn có thể làm kiểu đích của lambda dù không ghi annotation. Khi có annotation, thay đổi khiến interface không còn functional sẽ bị phát hiện ngay lúc biên dịch.

Annotation không tự tạo hành vi, không sinh phần thân cho phương thức abstract và không chứng minh thuật toán của lambda là đúng. Bài tiếp theo tập trung vào cách compiler kiểm tra annotation và cách nó giúp bảo vệ API khi được sửa đổi.

## 4. Khi nào nên dùng functional interface?

Dùng functional interface khi API cần nhận một hành vi đơn lẻ, chẳng hạn quy tắc so sánh, điều kiện lọc, phép biến đổi, callback hoặc tác vụ. Với hành vi phổ biến, ưu tiên kiểu chuẩn như `Predicate<T>`, `Function<T,R>` hoặc `Runnable` khi chữ ký phù hợp. Tạo interface riêng khi tên miền nghiệp vụ, tham số hoặc hợp đồng ngoại lệ cần được diễn đạt rõ hơn.

Trước khi chọn kiểu, hãy xác định hành vi cần đầu vào nào, kết quả ra sao và API nào sẽ gọi nó. Nếu một interface đòi hỏi nhiều hành vi abstract độc lập, hãy dùng một interface thông thường hoặc tách trách nhiệm thành các hợp đồng riêng.

## 5. Tự kiểm tra

1. Vì sao `IntOperation add = (a, b) -> a + b;` biên dịch được?  
   **Đáp án:** `IntOperation` cung cấp kiểu đích và quy định hai tham số `int` cùng kết quả `int`.

2. Interface có một `default` method và một abstract method có thể là functional interface không?  
   **Đáp án:** Có. Phương thức default đã có thân nên không tạo thêm nghĩa vụ abstract.

3. Vì sao `ReadWrite` không thể được triển khai bằng một lambda duy nhất?  
   **Đáp án:** Nó có hai phương thức abstract độc lập cần hai phần triển khai.

**Ghi nhớ:** Functional interface xác định một hợp đồng hàm mà lambda hoặc method reference có thể thực hiện. Hãy xét quy tắc chữ ký và kế thừa của Java, rồi chọn một kiểu đích diễn đạt đúng hành vi mà API cần nhận.