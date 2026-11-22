# Cam kết an toàn varargs và nguy cơ heap pollution trong Java

## Mục tiêu

Varargs (variable arity parameters) cho phép một phương thức nhận số lượng đối số thay đổi. Khi kết hợp với generic, varargs có thể tạo ra một mảng có kiểu phần tử không thể kiểm tra đầy đủ tại runtime. Nếu mảng này bị thay đổi hoặc bị đưa ra ngoài phạm vi kiểm soát, chương trình có thể rơi vào trạng thái *heap pollution* và phát sinh **ClassCastException** ở một vị trí khác với nơi gây ra lỗi.

Java cung cấp annotation **@SafeVarargs** để tác giả phương thức cam kết rằng cách triển khai varargs là an toàn. Annotation này là một cam kết về cách viết mã; nó không biến một phương thức nguy hiểm thành an toàn.

Bài này tập trung vào cú pháp và quy tắc vẫn áp dụng trong Java hiện đại, bao gồm Java 17+ và quy tắc **@SafeVarargs** cho private instance method được hỗ trợ từ Java 9.

## 1. Varargs hoạt động như thế nào?

Một tham số varargs được khai báo bằng dấu ba chấm:

```java
static void printNames(String... names) {
    for (String name : names) {
        System.out.println(name);
    }
}
```

Tham số varargs phải đứng cuối danh sách tham số. Khi gọi phương thức, có thể truyền không đối số, một đối số hoặc nhiều đối số:

```java
printNames();
printNames("An");
printNames("An", "Bình", "Chi");
```

Về bản chất, tham số varargs được xử lý như một mảng. Lời gọi **printNames("An", "Bình")** khiến trình biên dịch tạo hoặc sử dụng một mảng **String[]** để truyền vào phương thức. Nếu người gọi truyền thẳng một mảng tương thích, phương thức có thể nhận chính mảng đó; không nên giả định rằng mỗi lời gọi luôn tạo ra một bản sao mới.

Với kiểu phần tử reifiable như **String**, runtime biết kiểu phần tử thực của mảng. Rủi ro đặc biệt xuất hiện khi kiểu phần tử là generic không reifiable, ví dụ **List<String>** hoặc một type variable **T**.

## 2. Reifiable và non-reifiable type

Java dùng type erasure cho generic. Thông tin kiểu tham số như **String** trong **List<String>** không được lưu đầy đủ để runtime kiểm tra từng phần tử của collection.

- **Reifiable type**: kiểu mà thông tin cần thiết để kiểm tra kiểu có sẵn tại runtime.
- **Non-reifiable type**: kiểu có một phần thông tin generic bị xóa hoặc không thể xác định đầy đủ tại runtime.

Một số ví dụ:

| Kiểu | Phân loại | Lý do |
|---|---|---|
| **String** | Reifiable | Kiểu lớp cụ thể |
| **String[]** | Reifiable | Mảng của kiểu reifiable |
| **int[]** | Reifiable | Mảng kiểu nguyên thủy |
| **List<?>** | Reifiable | Tham số kiểu là unbounded wildcard |
| **List<String>** | Non-reifiable | Runtime không phân biệt được tham số **String** |
| **List<? extends Number>** | Non-reifiable | Wildcard có bound không phải unbounded wildcard |
| **T** | Non-reifiable | Type variable bị type erasure |
| **T[]** | Non-reifiable | Thành phần mảng phụ thuộc type variable |

Ví dụ, khai báo sau dùng kiểu phần tử non-reifiable:

```java
static void process(List<String>... groups) {
    // ...
}
```

Ở mã nguồn, tham số có kiểu **List<String>[]**. Nhưng kiểu phần tử **List<String>** không reifiable. Sau type erasure, kiểu runtime của mảng có component type là **List**, tương đương **List[]**; runtime không thể xác minh rằng từng phần tử bên trong thật sự là **List<String>**.

Vì vậy, trình biên dịch có thể cảnh báo:

- **Possible heap pollution from parameterized vararg type List<String>** tại khai báo phương thức.
- **unchecked generic array creation for varargs parameter** tại nơi gọi phương thức.

Có thể dùng **javac -Xlint:unchecked** để xem các cảnh báo unchecked liên quan.

## 3. Heap pollution là gì?

*Heap pollution* xảy ra khi một biến có kiểu tham số hóa tham chiếu đến một đối tượng không phù hợp với tham số kiểu mà mã nguồn đang tin cậy. Ví dụ, biến được khai báo là **List<String>** nhưng thực tế lại tham chiếu đến một **List<Integer>**.

Tình trạng này có thể xuất hiện khi kết hợp:

1. Generic type bị type erasure.
2. Varargs tạo một mảng có component type runtime không chứa đủ thông tin generic.
3. Mảng bị truy cập qua một kiểu rộng hơn như **Object[]**, hoặc bị đưa cho mã khác có thể ghi dữ liệu không phù hợp.
4. Giá trị sai kiểu được đọc lại qua biến generic; lỗi thường chỉ xuất hiện khi runtime thực hiện cast.

### Cơ chế gây lỗi

Xét tham số **List<String>... lists**:

- Ở compile time, mã nguồn xem mỗi phần tử là **List<String>**.
- Ở runtime, mảng thực tế là **List[]**.
- Vì mảng Java có tính covariance, một **List[]** có thể được gán cho biến **Object[]**.
- Runtime chỉ kiểm tra đối tượng được ghi có phải là **List** hay không. Nó không biết cần phải là **List<String>**.
- Nếu ghi **List<Integer>** vào mảng, phép ghi có thể thành công. Khi đọc phần tử và yêu cầu một **String**, cast được sinh bởi compiler có thể thất bại với **ClassCastException**.

## 4. Ví dụ hoàn chỉnh: tạo heap pollution và quan sát lỗi

Tạo tệp **VarargsHeapPollutionDemo.java**:

```java
import java.util.List;

public class VarargsHeapPollutionDemo {
    @SafeVarargs
    static <T> void printAll(T... values) {
        for (T value : values) {
            System.out.println(value);
        }
    }

    static void unsafe(List<String>... lists) {
        Object[] alias = lists;
        alias[0] = List.of(42);

        String first = lists[0].get(0);
        System.out.println(first);
    }

    public static void main(String[] args) {
        printAll("Java", "varargs");

        try {
            unsafe(List.of("safe"));
        } catch (ClassCastException exception) {
            System.out.println("Caught ClassCastException");
        }
    }
}
```

Biên dịch và chạy trên Java 9+:

```bash
javac -Xlint:unchecked VarargsHeapPollutionDemo.java
java VarargsHeapPollutionDemo
```

Với **javac 24.0.2**, trình biên dịch phát hai cảnh báo unchecked:

- Khai báo **unsafe(List<String>... lists)** có nguy cơ heap pollution từ tham số varargs không reifiable.
- Lời gọi **unsafe(List.of("safe"))** tạo mảng generic varargs không được kiểm tra đầy đủ.

Stdout khi chạy:

```text
Java
varargs
Caught ClassCastException
```

Giải thích:

1. **unsafe(List.of("safe"))** nhận một mảng runtime có component type là **List**.
2. **Object[] alias = lists** tạo một tham chiếu khác tới cùng mảng; không sao chép mảng.
3. **alias[0] = List.of(42)** được runtime chấp nhận vì **List.of(42)** là một đối tượng **List**. Runtime không kiểm tra tham số generic **String** hay **Integer**.
4. Biểu thức **lists[0].get(0)** được compiler xem là trả về **String**. Khi đối tượng thực tế là **Integer**, cast sang **String** thất bại.
5. Exception được bắt trong **main**, vì vậy chương trình tiếp tục và in dòng thông báo cuối.

Heap pollution không nhất thiết gây lỗi ngay tại câu lệnh làm sai dữ liệu. Lỗi có thể chỉ xuất hiện về sau, tại nơi dữ liệu được đọc và cast.

## 5. @SafeVarargs cam kết điều gì?

**@SafeVarargs** là annotation chuẩn của Java dành cho khai báo constructor hoặc phương thức varargs. Nó thể hiện rằng tác giả cam kết cách triển khai không thực hiện thao tác gây heap pollution thông qua tham số varargs không reifiable.

Ví dụ sau là một cách dùng an toàn: phương thức chỉ đọc từng phần tử, xử lý phần tử rồi không thay đổi hoặc để lộ mảng varargs.

```java
@SafeVarargs
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

### Những nơi được phép dùng annotation

**@SafeVarargs** chỉ áp dụng cho constructor hoặc phương thức có tham số varargs. Với phương thức, khai báo phải là một trong các trường hợp:

- **static**: không thể bị override theo cơ chế phương thức instance.
- **final**: lớp con không thể override phương thức.
- **private**: phương thức không thể bị override.

Constructor cũng có thể dùng annotation này vì constructor không phải phương thức được override. Từ Java 9, private instance method được phép dùng **@SafeVarargs**; quy tắc này vẫn áp dụng trong các phiên bản Java hiện đại.

Ví dụ về private instance method:

```java
class Logger {
    @SafeVarargs
    private void logAll(String... messages) {
        for (String message : messages) {
            System.out.println(message);
        }
    }
}
```

Một phương thức instance có thể bị override và không phải **final** hoặc **private** không được gắn **@SafeVarargs**. Trình biên dịch báo lỗi nếu annotation được dùng trên khai báo không đủ điều kiện.

### Annotation không tự làm mã an toàn

**@SafeVarargs** không:

- Thay đổi kiểu mảng runtime hoặc khôi phục thông tin generic đã bị xóa.
- Tự động sao chép mảng varargs.
- Chặn phép ghi sai kiểu qua một alias như **Object[]**.
- Kiểm tra toàn bộ logic phương thức để chứng minh cam kết luôn đúng.
- Ngăn **ClassCastException** nếu phần thân phương thức vẫn tạo ra heap pollution.

Annotation cho phép trình biên dịch bỏ qua các cảnh báo unchecked liên quan tới việc truyền tham số varargs cho khai báo đã được cam kết an toàn. Nếu cam kết sai, chương trình vẫn có thể gặp lỗi runtime. Một số cảnh báo **-Xlint:varargs** về thao tác nguy hiểm ngay bên trong thân phương thức vẫn có thể xuất hiện.

## 6. Cách viết phương thức varargs an toàn

Khi dùng kiểu phần tử non-reifiable như **T** hoặc **List<String>**, hãy kiểm soát chặt cách sử dụng mảng varargs.

### Nên làm

- Đọc từng phần tử bằng kiểu generic đã khai báo.
- Xử lý phần tử mà không thay đổi vị trí phần tử trong mảng varargs.
- Không để lộ tham chiếu tới mảng cho mã bên ngoài.
- Nếu cần lưu dữ liệu, tạo collection mới và sao chép từng phần tử vào collection đó.
- Chỉ thêm **@SafeVarargs** sau khi đã kiểm tra toàn bộ thân phương thức và các phương thức được gọi bên trong.

### Tránh làm

- Gán mảng varargs vào **Object[]** rồi ghi đối tượng không bảo đảm tương thích với kiểu generic.
- Ép kiểu unchecked hoặc dùng raw type để đưa phần tử sai kiểu vào mảng.
- Trả trực tiếp mảng varargs cho bên gọi.
- Lưu mảng varargs để dùng ở nơi khác có thể thay đổi nó.
- Truyền mảng cho phương thức khác mà không biết phương thức đó có ghi hoặc làm lộ mảng hay không.
- Gắn **@SafeVarargs** chỉ để che cảnh báo mà không kiểm tra hành vi thực tế.

Đặc biệt, **Arrays.asList(values)** tạo một list có kích thước cố định nhưng được backing bởi chính mảng truyền vào. Nếu trả list này ra ngoài, bên nhận vẫn có thể thay đổi phần tử và tác động tới mảng varargs ban đầu. Khi cần trả về dữ liệu độc lập, hãy tạo bản sao collection phù hợp thay vì để lộ mảng.

## 7. Khi nào nên dùng List<T> thay cho generic varargs?

Varargs thuận tiện khi API thực sự nhận một số lượng đối số nhỏ, thường được truyền trực tiếp tại chỗ. Tuy nhiên, nếu dữ liệu bản chất là một tập hợp generic, tham số **List<T>** hoặc **Collection<T>** thường biểu đạt ý định rõ hơn và tránh việc tạo mảng generic varargs.

Ví dụ:

```java
static <T> void processAll(List<T> values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

Lời gọi:

```java
processAll(List.of("Java", "Generic", "Varargs"));
```

Không cần annotation **@SafeVarargs** vì phương thức không có tham số varargs.

Nếu API cần cú pháp gọi thuận tiện như **processAll(a, b, c)**, có thể giữ varargs, nhưng phải xác định rõ phương thức có thật sự an toàn với mảng generic được tạo tại call site hay không.

## 8. Phân biệt @SafeVarargs và @SuppressWarnings

Hai annotation có mục đích khác nhau:

| Annotation | Ý nghĩa |
|---|---|
| **@SafeVarargs** | Cam kết rằng triển khai varargs là an toàn đối với heap pollution; được dùng trên constructor hoặc phương thức varargs đủ điều kiện |
| **@SuppressWarnings("unchecked")** | Yêu cầu trình biên dịch không hiển thị cảnh báo unchecked trong phạm vi được gắn annotation |

**@SuppressWarnings("unchecked")** chỉ kiểm soát cảnh báo. Nó không phải bằng chứng rằng một thao tác generic là an toàn và không thay đổi hành vi runtime.

Không nên thay **@SafeVarargs** bằng **@SuppressWarnings("unchecked")** chỉ để làm sạch output biên dịch. Trước tiên phải xác định nguyên nhân cảnh báo và sửa cách dùng mảng hoặc kiểu dữ liệu nếu có nguy cơ heap pollution.

## 9. Các lỗi và hiểu nhầm thường gặp

1. **Cho rằng generic varargs luôn an toàn vì compiler cho phép khai báo**: trình biên dịch có thể phát cảnh báo vì runtime không kiểm tra đầy đủ tham số generic của mảng.
2. **Cho rằng @SafeVarargs ngăn heap pollution**: annotation chỉ là cam kết và cơ chế xử lý cảnh báo; mã triển khai vẫn có thể sai.
3. **Nghĩ Object[] alias = values tạo bản sao**: phép gán chỉ tạo thêm một tham chiếu tới cùng mảng.
4. **Nghĩ phép ghi List<Integer> vào List[] phải bị chặn**: runtime chỉ thấy component type List, nên phép ghi có thể thành công.
5. **Không hiểu vì sao lỗi xuất hiện tại lệnh đọc**: cast do generic type erasure có thể thất bại sau khi dữ liệu đã bị làm sai ở một vị trí trước đó.
6. **Dùng @SafeVarargs trên phương thức có thể bị override**: phương thức instance phải là final hoặc private; phương thức static cũng đủ điều kiện.
7. **Để lộ mảng varargs qua giá trị trả về hoặc collection backing**: bên nhận có thể sửa mảng sau khi phương thức đã kiểm tra dữ liệu.
8. **Dùng raw type hoặc unchecked cast để né cảnh báo**: các thao tác này làm mất kiểm tra kiểu ở compile time và có thể đưa dữ liệu không phù hợp vào mảng.

## 10. Quy trình kiểm tra khi viết API generic varargs

1. Xác định kiểu phần tử có reifiable hay không. Nếu là **T**, **List<String>** hoặc kiểu generic có tham số cụ thể, xem xét nguy cơ trước tiên.
2. Xác định phương thức có nhận mảng được tạo tại call site hay có thể nhận mảng có sẵn từ người gọi.
3. Kiểm tra xem thân phương thức có ghi vào mảng, ép kiểu unchecked, lưu mảng, trả mảng hoặc truyền mảng cho mã khác có thể thay đổi nó không.
4. Nếu có thể biểu đạt API bằng **List<T>** hoặc **Collection<T>**, cân nhắc dùng collection.
5. Chỉ thêm **@SafeVarargs** khi đã chứng minh bằng cách đọc mã rằng triển khai không tạo heap pollution.
6. Biên dịch với **javac -Xlint:unchecked** và xem cả cảnh báo ở khai báo lẫn nơi gọi. Sau đó chạy ví dụ hoặc test để kiểm tra hành vi thực tế.

## Kết luận

Varargs được triển khai dựa trên mảng. Khi kiểu phần tử là generic non-reifiable, type erasure khiến runtime không thể kiểm tra đầy đủ tham số kiểu của từng phần tử. Nếu mảng bị thay đổi qua alias hoặc bị để lộ, heap pollution có thể xảy ra và gây **ClassCastException** ở thời điểm đọc dữ liệu.

**@SafeVarargs** là cam kết của người viết API rằng việc sử dụng tham số varargs an toàn. Hãy chỉ dùng annotation sau khi đã kiểm soát việc đọc, ghi và chia sẻ mảng; nếu dữ liệu là một tập hợp generic, **List<T>** hoặc **Collection<T>** thường là lựa chọn rõ ràng hơn.
