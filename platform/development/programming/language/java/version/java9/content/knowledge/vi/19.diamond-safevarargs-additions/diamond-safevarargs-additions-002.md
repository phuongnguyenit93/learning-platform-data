# Giới hạn của kiểu suy luận có thể biểu diễn trong mã nguồn

Java hỗ trợ trình biên dịch tự suy luận tham số kiểu của generic thay vì bắt người viết lặp lại cùng một kiểu ở nhiều vị trí. Toán tử kim cương `<>` là một cách dùng phổ biến: kiểu tham số được suy ra từ đối số constructor và ngữ cảnh đích, chẳng hạn kiểu biến nhận kết quả.

Việc suy luận có giới hạn. Một số kiểu mà trình biên dịch tạo ra trong quá trình kiểm tra generic chỉ tồn tại nội bộ, không có cú pháp Java để viết tên trực tiếp. Java gọi kiểu có thể viết được trong mã nguồn là *denotable type*. Giới hạn này đặc biệt dễ thấy khi kết hợp `<>` với lớp vô danh (anonymous class), một khả năng được hỗ trợ từ Java 9.

## 1. Kiểu suy luận đến từ đâu?

Khi gặp `new ArrayList<>()`, trình biên dịch dùng các ràng buộc kiểu có sẵn để xác định tham số `E` của `ArrayList<E>`. Hai nguồn thông tin thường gặp là:

- **Ngữ cảnh đích (target type):** kiểu của biến nhận kết quả, kiểu trả về hoặc kiểu tham số mà biểu thức được truyền vào có thể giúp xác định tham số generic.
- **Đối số constructor:** kiểu của các đối số được truyền cho constructor giúp suy ra kiểu phần tử phù hợp.

Ví dụ, kiểu `String` được suy ra từ kiểu đích `List<String>`:

```java
List<String> names = new ArrayList<>();
```

Trong ví dụ khác, kiểu `Integer` được suy ra từ collection truyền cho constructor:

```java
List<Integer> source = List.of(10, 20, 30);
ArrayList<Integer> copy = new ArrayList<>(source);
```

Trình biên dịch giải các ràng buộc theo quy tắc của hệ thống kiểu Java. Nó không đoán ý định của người viết và không thể tự tạo một kiểu có tên tùy ý để biểu diễn mọi kết quả suy luận.

## 2. Denotable type và kiểu capture

Một kiểu là *denotable* khi có thể biểu diễn nó bằng cú pháp kiểu hợp lệ trong mã nguồn Java. Ví dụ:

- `String`
- `List<String>`
- `ArrayList<Object>`
- `List<?>`

Wildcard `?` là cú pháp hợp lệ trong mã nguồn. Tuy nhiên, khi một biểu thức cần làm việc với `List<?>`, trình biên dịch thường tạo một **capture variable** nội bộ để đại diện cho kiểu thực tế bị ẩn sau wildcard. Thông báo lỗi có thể hiển thị tên như `CAP#1` hoặc `CAP#2`.

`CAP#1` không phải tên kiểu mà lập trình viên có thể khai báo hoặc viết trực tiếp trong mã nguồn. Nó đại diện cho một kiểu cụ thể nhưng chưa biết, có các giới hạn do wildcard quy định. Vì vậy, capture type không đồng nghĩa với `Object`: chương trình có thể đọc phần tử của `List<?>` dưới dạng `Object`, nhưng không thể tùy ý thêm một `Object` bất kỳ vào danh sách đó.

Phân biệt hai ý này rất quan trọng: `List<?>` là kiểu có thể viết trong source code; kiểu capture mà trình biên dịch tạo ra từ wildcard thì không thể được gọi tên như một type argument thông thường.

## 3. Diamond operator với anonymous class

Từ Java 9, có thể dùng `<>` khi tạo một anonymous class, miễn là kiểu được suy ra có thể biểu diễn trong chữ ký generic của lớp được sinh ra. Ngữ cảnh đích có thể cung cấp kiểu cụ thể:

```java
List<String> names = new ArrayList<>() {
    @Override
    public boolean add(String value) {
        return super.add(value.strip());
    }
};

names.add("  Linh  ");
System.out.println(names);
```

Ở đây kiểu đích là `List<String>`, vì vậy kiểu superclass được suy ra là `ArrayList<String>`. Đây là kiểu có thể biểu diễn trong mã nguồn và trong generic signature của class file. Ví dụ dùng `String.strip()`, có từ Java 11; bản thân khả năng dùng diamond với anonymous class có từ Java 9 và vẫn được hỗ trợ trong Java hiện đại.

Với anonymous class, trình biên dịch phải tạo một class file cho lớp vô danh và ghi thông tin kiểu generic của superclass vào metadata chữ ký (`Signature` attribute) khi cần. Do đó, kiểu được suy ra phải có dạng có thể biểu diễn trong chữ ký này.

## 4. Trường hợp không thể suy luận thành kiểu biểu diễn được

Xét một phương thức trả về `List<?>`:

```java
private static List<?> unknownValues() {
    return List.of("Java", 9);
}
```

Nếu dùng diamond cùng anonymous class như sau, trình biên dịch không thể tạo kiểu superclass phù hợp:

```java
ArrayList<?> copy = new ArrayList<>(unknownValues()) {
};
```

Constructor nhận `List<?>`. Để suy ra tham số phần tử, trình biên dịch phải dùng capture type, ví dụ `CAP#1`. Kiểu superclass của anonymous class khi đó cần trở thành `ArrayList<CAP#1>`. Vì `CAP#1` là kiểu capture nội bộ, không thể biểu diễn trong generic signature như một type argument thông thường, nên biểu thức này bị từ chối khi biên dịch.

Thông báo của `javac` có thể nêu rõ rằng type argument được suy ra không được phép trong ngữ cảnh này vì nó không thể biểu diễn trong `Signature` attribute. Câu chữ và tên capture (`CAP#1`, `CAP#2`...) có thể khác giữa phiên bản trình biên dịch, nhưng nguyên nhân vẫn là kiểu suy luận không denotable.

Đây là giới hạn ở thời điểm biên dịch. Trình biên dịch không thể biến một capture type nội bộ thành một kiểu tham số có tên hợp lệ chỉ để hoàn tất khai báo superclass của anonymous class.

## 5. Cách xử lý

**Cách 1: Chọn một kiểu tường minh có thể biểu diễn.** Nếu chương trình chỉ cần giữ các phần tử dưới dạng `Object`, có thể chỉ rõ type argument:

```java
ArrayList<Object> copy =
        new ArrayList<Object>(unknownValues()) {
};
```

Điều này an toàn vì mọi phần tử trong `List<?>` đều là object và có thể được lưu trong `ArrayList<Object>`. Tuy nhiên, lựa chọn `Object` làm mất thông tin kiểu phần tử cụ thể; chỉ dùng khi phần còn lại của chương trình chấp nhận làm việc với `Object`.

**Cách 2: Bỏ anonymous class nếu không cần hành vi bổ sung.** Một biểu thức tạo đối tượng thông thường không cần khai báo superclass cho một lớp vô danh, nên có thể giữ diamond:

```java
List<?> copy = new ArrayList<>(unknownValues());
```

**Cách 3: Đặt hành vi bổ sung vào một lớp hoặc phương thức generic có tên.** Nếu cần mở rộng hành vi, hãy thiết kế tham số kiểu tại API của lớp hoặc phương thức đó để kiểu đầu vào, kiểu đầu ra và giới hạn của nó được thể hiện rõ ràng. Chọn một kiểu cụ thể hoặc upper bound phù hợp khi gọi API.

Không nên dùng raw type hoặc unchecked cast chỉ để làm cho biểu thức biên dịch. Cách đó che giấu ràng buộc kiểu và có thể đẩy lỗi sang thời điểm chạy.

## 6. Những điểm dễ nhầm

- `List<?>` là kiểu hợp lệ có thể viết trong source; capture type được tạo từ wildcard mới là phần không thể gọi tên trực tiếp.
- Capture type không tự động trở thành `Object`. `Object` là kiểu cha mà mọi reference type có thể gán vào, còn capture type giữ ràng buộc của wildcard cụ thể.
- Diamond operator không bỏ qua kiểm tra kiểu. `<>` chỉ yêu cầu trình biên dịch suy luận type argument từ các ràng buộc hợp lệ.
- Việc gán kết quả cho `List<?>` không đảm bảo mọi biểu thức tạo anonymous class đều có thể dùng capture type làm superclass argument. Anonymous class còn cần một generic signature biểu diễn được.
- Giới hạn này không có nghĩa là không thể sao chép một `List<?>`. Ví dụ `new ArrayList<>(unknownValues())` vẫn hợp lệ nếu không thêm anonymous class như trường hợp trên.

## 7. Quy trình kiểm tra khi gặp lỗi suy luận kiểu

1. Xác định generic type nào đang được suy luận và các ràng buộc đến từ target type hay constructor arguments.
2. Đọc phần `CAP#...` trong thông báo lỗi để nhận biết trình biên dịch đang dùng wildcard capture.
3. Kiểm tra biểu thức có tạo anonymous class hay cần ghi một generic signature hay không.
4. Nếu cần anonymous class, chọn một type argument tường minh có thể biểu diễn và vẫn an toàn về mặt kiểu.
5. Nếu không cần anonymous class, bỏ phần thân lớp vô danh để giữ biểu thức tạo đối tượng thông thường.
6. Biên dịch lại với phiên bản Java mục tiêu của dự án; không dùng raw type hoặc ép kiểu không kiểm tra để che lỗi.

Kiểu suy luận giúp mã generic ngắn gọn nhưng luôn tuân theo những kiểu mà Java có thể biểu diễn và kiểm tra. Khi kết quả suy luận là một capture type không thể gọi tên, đặc biệt trong diamond operator với anonymous class, hãy chọn một kiểu tường minh an toàn hoặc thay đổi cấu trúc để không cần ghi kiểu đó vào generic signature.