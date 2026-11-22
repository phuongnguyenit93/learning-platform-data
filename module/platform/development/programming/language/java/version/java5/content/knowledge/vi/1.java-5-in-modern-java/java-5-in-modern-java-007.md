# Tra cứu đặc tả ngôn ngữ và trạng thái API trên JDK đang sử dụng

## 1. Tính năng có nguồn gốc từ Java 5 vẫn cần đọc theo môi trường hiện tại

Generics, enum, boxing và vòng lặp for-each vẫn là các khái niệm đang được dùng trong Java hiện đại. Nhưng một ví dụ có những cú pháp đó có thể đồng thời gọi API được bổ sung ở một bản Java sau. Không nên suy ra cả đoạn mã chạy được trên một môi trường chỉ từ tên chương kiến thức.

Khi cần kiểm chứng một khẳng định, tách ba câu hỏi:

1. **Ngôn ngữ cho phép điều gì?** Tra Java Language Specification, viết tắt JLS.
2. **Một API cụ thể có hợp đồng/trạng thái gì?** Tra Java API Specification của đúng phiên bản.
3. **Dự án thật đang dùng cấu hình nào?** Kiểm tra JDK biên dịch, mức release và runtime chạy.

Bài này dùng tài liệu Java SE 21 làm ví dụ đường dẫn có phiên bản. Khi dự án dùng phiên bản khác, chọn bộ tài liệu tương ứng; không mặc định trang 21 là trạng thái của mọi JDK hoặc là bản mới nhất.

## 2. Chốt môi trường trước khi tra cứu

Trong terminal của dự án, kiểm tra các công cụ thực sự được gọi:

```shell
java -version
javac -version
javac --help
```

Kết quả phiên bản phụ thuộc máy, không có một stdout chung cho mọi người. `java` và `javac` trên `PATH` có thể đến từ hai cài đặt khác nhau. Biến `JAVA_HOME`, JDK của IDE và JDK do công cụ build chọn cũng có thể khác terminal.

Với Gradle wrapper, kiểm tra thêm thông tin môi trường build:

```shell
./gradlew --version
```

Trên Windows có thể dùng `gradlew.bat --version`. Nếu build dùng Java toolchain, cần đọc cấu hình toolchain và nhiệm vụ biên dịch tương ứng; JVM chạy Gradle không bắt buộc là JDK dùng để biên dịch source.

Lưu lại ít nhất: JDK compiler, mức release mục tiêu và runtime dùng khi chạy kiểm tra. Thiếu một trong ba, câu “máy tôi biên dịch được” chưa đủ để kết luận khả năng chạy ở nơi khác.

## 3. release là hợp đồng khác với chỉ phiên bản compiler

`javac --release N` yêu cầu biên dịch theo phiên bản nền tảng được hỗ trợ đó, bao gồm quy tắc ngôn ngữ, định dạng class file và API nền tảng được cung cấp cho quá trình biên dịch.

Đó là lý do `--release` khác với chỉ chỉnh `-source`/`-target`: chỉ đổi cú pháp và class file có thể vẫn để mã vô tình gọi API quá mới nếu không kiểm soát API nền tảng.

Không phải mọi JDK đều hỗ trợ mọi giá trị release; xem `javac --help` của chính compiler đang dùng. `--release` cũng không cài một runtime tương ứng và không kiểm tra đầy đủ tính tương thích của mọi thư viện bên thứ ba.

Ví dụ: for-each và `List<Integer>` là ngôn ngữ; `List.of(...)` là lời gọi thư viện. Một compiler có thể hiểu for-each nhưng API mục tiêu lại không có `List.of`. Lỗi tìm không thấy phương thức trong trường hợp đó là vấn đề API/cấu hình, không phải for-each ngừng hoạt động. [javac: tùy chọn biên dịch](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)

## 4. Chọn đúng nơi tra theo loại câu hỏi

| Câu hỏi | Nơi tra chính |
| --- | --- |
| For-each nhận kiểu nguồn nào, chuyển đổi biến vòng lặp ra sao? | JLS §14.14.2 |
| Khi nào có boxing/unboxing, null gây lỗi ở đâu? | JLS §5.1.7 và §5.1.8 |
| Phần tử annotation được phép có kiểu nào? | JLS §9.6.1 |
| Enum có những ràng buộc ngôn ngữ nào? | JLS §8.9 |
| `List.of` có nhận null hoặc cho sửa danh sách không? | Javadoc của `List` và đúng overload |
| `setObject` có thể ném lỗi gì? | Javadoc JDBC và tài liệu driver cụ thể |

JLS là đặc tả quy tắc ngôn ngữ, không phải danh mục hợp đồng của mọi phương thức thư viện. Ngược lại, ví dụ trong Javadoc không thay cho toàn bộ quy tắc chuyển đổi kiểu. [Mục lục JLS Java SE 21](https://docs.oracle.com/javase/specs/jls/se21/html/index.html)

Cách đọc hiệu quả là bắt đầu từ câu hỏi nhỏ. Ví dụ “for-each chỉ dùng được với `List` không?” dẫn đến phần enhanced for, nơi quy tắc nói đến mảng và `Iterable`, thay vì đọc ngẫu nhiên cả chương collections. [JLS §14.14.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.14.2)

## 5. Đọc API ở đúng phần tử, không chỉ tên lớp

Khi mở API docs, kiểm tra phiên bản trang rồi đọc:

- Module/package và tên kiểu đầy đủ.
- Chữ ký, tham số kiểu, kiểu trả về và đúng overload.
- Hợp đồng hành vi, tham số được phép, trường hợp `null`.
- `Throws`, `Since`, và các phần API Note/Implementation Requirements khi liên quan.
- Thông báo deprecation hoặc trạng thái đặc biệt của đúng phần tử.

`Since` trên một lớp không có nghĩa mọi phương thức của nó đã có từ cùng phiên bản. Phương thức thêm sau sẽ có thông tin riêng. `List` tồn tại từ trước, nhưng các factory `of` được thêm vào Java 9; phải tra đúng phương thức nếu cần xác định khả năng sử dụng.

Từ đó, phân biệt **có API** với **hành vi của kết quả**. `List.of` trả danh sách không cho sửa và không chấp nhận `null`; thấy phương thức trong compiler không chứng minh dùng `add` trên kết quả là hợp lệ. [List: danh sách không cho sửa](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)

## 6. Trạng thái API: không gộp thành “mới” hoặc “cũ”

| Trạng thái/thông tin | Điều có thể kết luận | Không được tự suy ra |
| --- | --- | --- |
| Có trong bản API đang đọc | API thuộc bản đó theo tài liệu | Có trong mọi release cũ hơn |
| `Deprecated` | Không khuyến khích dùng; đọc lý do/thay thế | Đã bị xóa hoặc chắc chắn ngừng chạy |
| `forRemoval=true` | Có ý định loại bỏ trong tương lai | Một ngày loại bỏ cụ thể nếu chưa công bố |
| Đã bị loại bỏ | Không còn API đó trong bản mục tiêu | Một cờ cảnh báo có thể khôi phục đầy đủ |
| Preview | Cần đọc quy tắc kích hoạt và ràng buộc phiên bản | API/tính năng đã ổn định cho mọi runtime |
| API nội bộ của JDK | Phụ thuộc ngoài hợp đồng API chuẩn được hỗ trợ | Bền vững chỉ vì hôm nay vẫn gọi được |

`@Deprecated(since=..., forRemoval=...)` và mô tả `@deprecated` cung cấp thông tin để quyết định. Không coi “không deprecated” là chứng nhận mọi cách dùng đều an toàn, và không coi tuổi đời lâu là lý do tự động tránh một API còn phù hợp. [Deprecated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Deprecated.html)

Nếu gặp preview trong tài liệu, xác minh bằng bộ docs và hướng dẫn công cụ của đúng release; không bật preview chỉ để một ví dụ không liên quan biên dịch. Bài này chỉ dùng các tính năng ổn định.

## 7. Chương trình minh chứng một câu hỏi từ đặc tả

Thay vì chỉ đọc mô tả, tạo một ví dụ tối thiểu để kiểm chứng phần liên quan. Chương trình sau nối generic `List<Integer>`, for-each và unboxing; nó cũng kiểm tra hợp đồng không sửa được của `List.of`.

Lưu thành `SpecLookupDemo.java`:

```java
import java.util.List;

public class SpecLookupDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 3, 5);
        int total = 0;
        for (int value : values) {
            total += value;
        }
        System.out.println("total=" + total);
        try {
            values.add(7);
        } catch (UnsupportedOperationException ex) {
            System.out.println("listIsUnmodifiable");
        }
    }
}
```

Biên dịch và chạy bằng JDK hỗ trợ release 17:

```shell
javac --release 17 -Xlint:deprecation -Xlint:removal SpecLookupDemo.java
java SpecLookupDemo
```

Stdout chính xác:

```text
total=10
listIsUnmodifiable
```

Ví dụ đủ nhỏ để xác định từng cơ chế: `List.of` cung cấp danh sách; for-each lấy phần tử; gán vào `int` thực hiện unboxing; lời gọi `add` bị từ chối theo hợp đồng collection. Một lần chạy là bằng chứng cho ví dụ và môi trường đó, không thay thế đặc tả cho mọi đầu vào.

## 8. Dùng công cụ để bổ sung bằng chứng

### Cảnh báo compiler

`-Xlint:deprecation` và `-Xlint:removal` giúp lộ việc dùng API bị đánh dấu tương ứng. Không thêm `@SuppressWarnings` chỉ để xóa dấu hiệu trước khi đọc nguyên nhân và hướng thay thế.

### Xem chữ ký và bytecode

```shell
javap -classpath . -public SpecLookupDemo
javap -classpath . -c SpecLookupDemo
```

`javap` cho phép xem thành phần class file và bytecode, hữu ích để quan sát lời gọi và chuyển đổi mà compiler tạo. Đừng yêu cầu mọi compiler tối ưu theo một chuỗi bytecode giống hệt nhau nếu đặc tả chỉ quy định kết quả hành vi. [javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html)

### Quét mã đã biên dịch

```shell
jdeprscan SpecLookupDemo.class
jdeps --jdk-internals SpecLookupDemo.class
```

`jdeprscan` tìm sử dụng API deprecated do Java SE định nghĩa; nó không quét đầy đủ trạng thái deprecation của thư viện bên thứ ba. Với nhiều lớp phụ thuộc, cần classpath đúng. `jdeps --jdk-internals` giúp nhận diện phụ thuộc API nội bộ, nhưng phân tích tĩnh không khám phá đầy đủ mọi tên lớp nạp động hoặc reflection từ chuỗi. [jdeprscan](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html), [jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)

Không có cảnh báo trong một lần quét không đồng nghĩa toàn bộ ứng dụng tương thích mọi JDK hoặc mọi cách triển khai. Kết hợp tài liệu, cấu hình compiler và kiểm tra chạy ở runtime mục tiêu.

## 9. Ghi kết luận có thể kiểm tra lại

Một ghi chú kỹ thuật hữu ích có thể viết theo cấu trúc:

```text
Câu hỏi: nguồn nào dùng được với enhanced for?
Phạm vi: quy tắc ngôn ngữ Java SE 21; ví dụ biên dịch --release 17.
Nguồn: JLS §14.14.2.
Bằng chứng: ví dụ tối thiểu dùng List<Integer>, tổng bằng 10.
Phân biệt: List.of là API thư viện, không phải cú pháp của vòng lặp.
```

Nhờ vậy, người đọc biết khẳng định áp dụng cho điều gì, tài liệu nào và phần nào đã kiểm chứng. Khi thay JDK hoặc dependency, có thể quay lại đúng giả định thay vì đọc lại toàn bộ bài.

Nếu tài liệu và thực nghiệm khác nhau, trước hết kiểm tra phiên bản tài liệu, compiler thực tế, `--release`, overload được chọn, dependency và cấu hình runtime. Không vội kết luận đặc tả sai từ một ví dụ chưa cô lập.

## 10. Tự thực hành

1. Tra quy tắc unboxing `null` và tạo ví dụ tối thiểu gây đúng lỗi.
2. Chọn một API đang dùng trong dự án; ghi `Since`, hợp đồng `null`, ngoại lệ và trạng thái của đúng overload.
3. So sánh JDK của terminal với toolchain build và cấu hình IDE.
4. Chạy `javap -c` cho ví dụ rồi liên hệ lời gọi đọc phần tử/unboxing với mô tả ngôn ngữ.

Mục tiêu là một thói quen tra cứu có phạm vi rõ: đúng phiên bản, đúng loại nguồn, đúng phần tử API và có bằng chứng phù hợp với kết luận.