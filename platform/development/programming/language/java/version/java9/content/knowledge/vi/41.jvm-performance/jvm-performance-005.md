# Compiler Control và chỉ thị biên dịch theo phương thức

Compiler Control là cơ chế của HotSpot cho phép áp dụng tùy chọn JIT theo từng phương thức. Thay vì thay đổi một cờ toàn cục ảnh hưởng đến cả ứng dụng, ta có thể viết các directive để yêu cầu compiler xử lý một nhóm method cụ thể theo cách riêng: loại method khỏi biên dịch, điều chỉnh inlining, giới hạn log biên dịch hoặc bật thông tin chẩn đoán.

Tính năng này được giới thiệu trong JDK 9 qua JEP 165 và vẫn có trong các bản HotSpot hiện hành. Compiler Control hữu ích khi điều tra hành vi JIT, tạo bài kiểm thử compiler có thể lặp lại và thử một workaround giới hạn cho method gặp vấn đề. Đây là cơ chế riêng của HotSpot, không phải API Java chuẩn mà mọi JVM đều phải triển khai.

## 1. Vì sao cần điều khiển biên dịch theo method?

HotSpot tự theo dõi hoạt động của chương trình và quyết định khi nào biên dịch method. Với tiered compilation, code có thể đi qua interpreter và các tầng biên dịch C1/C2 trước khi đạt mức tối ưu phù hợp. Quyết định này dựa trên profile và heuristic của JVM.

Thông thường nên để JVM tự tối ưu. Tuy nhiên, khi cần chẩn đoán một method hoặc kiểm thử một giả thuyết, việc thay đổi cờ toàn cục có thể ảnh hưởng nhiều method không liên quan. Compiler Control cho phép khoanh vùng:

- Loại riêng một method khỏi JIT để so sánh hành vi interpreter với compiled code.
- Ngăn hoặc thử inlining một method trong một ngữ cảnh cụ thể.
- Chỉ bật compilation log hoặc thông tin inlining cho method đang điều tra.
- Thử các tùy chọn compiler riêng cho C1 hoặc C2.
- Thêm hoặc gỡ directive khi JVM đang chạy bằng diagnostic command.

Directive tác động đến quyết định biên dịch của HotSpot. Nó không thay đổi logic Java, kết quả nghiệp vụ hoặc hợp đồng của method. Nếu đặt `Exclude: true`, method vẫn chạy được, nhưng HotSpot không biên dịch method đó theo directive tương ứng và có thể thực thi nó bằng interpreter.

## 2. Compiler Control, C1 và C2

HotSpot có thể sử dụng nhiều tầng biên dịch. Trong chế độ tiered compilation mặc định, C1 thường tạo code nhanh hơn với các mức profiling khác nhau; C2 thực hiện tối ưu sâu hơn khi method đủ nóng. Chi tiết tầng nào được sử dụng còn phụ thuộc cấu hình runtime và nền tảng.

Một directive có thể có ba vùng tùy chọn:

| Vùng | Phạm vi |
|---|---|
| `c1` | Chỉ áp dụng cho compiler C1 |
| `c2` | Chỉ áp dụng cho compiler C2 |
| Common block | Các tùy chọn chung, đặt trực tiếp trong directive ngoài `c1` và `c2` |

Ví dụ:

```json
{
  "match": "com/example/Service.process",
  "c1": {
    "Exclude": true
  },
  "c2": {
    "PrintInlining": true
  },
  "Log": true
}
```

Trong ví dụ này, method khớp pattern bị loại khỏi C1, C2 bật thông tin inlining, còn `Log` là tùy chọn chung. Các tùy chọn phải được compiler tương ứng hỗ trợ; một option chỉ dành cho C2 cần được đặt trong block `c2`.

Không phải mọi bản dựng JVM đều cung cấp toàn bộ tùy chọn chẩn đoán. Một số tùy chọn yêu cầu diagnostic flag hoặc debug build. Luôn kiểm tra tài liệu của đúng runtime đang chạy.

## 3. Tạo directive file

Compiler directives được lưu trong một file có cấu trúc gần JSON. Một file có thể chứa nhiều directive block trong một mảng. Mỗi block có `match` để chọn method và các tùy chọn điều khiển compilation.

Ví dụ file `compiler-directives.json`:

```json
[
  {
    "match": "com/example/Service.process",
    "c2": {
      "Exclude": true
    }
  },
  {
    "match": "com/example/Parser.*",
    "c1": {
      "PrintInlining": true
    },
    "c2": {
      "PrintInlining": true
    }
  }
]
```

Các điểm cần nhớ:

- `match` nhận một hoặc nhiều method pattern.
- Một directive block có thể chứa tùy chọn C1, C2 và tùy chọn chung.
- Có thể có nhiều block trong cùng file.
- Thứ tự block quan trọng: directive phù hợp có độ ưu tiên cao hơn ở phía đầu file.
- File directive được kiểm tra khi nạp. Nếu cú pháp hoặc directive không hợp lệ, JVM có thể báo lỗi và không khởi động ứng dụng.

HotSpot chấp nhận một số mở rộng nhỏ ngoài JSON nghiêm ngặt, như tên thuộc tính không đặt trong dấu ngoặc kép và dấu phẩy cuối. Trong dự án, nên dùng JSON chuẩn với tên thuộc tính và chuỗi đều có dấu ngoặc kép để dễ kiểm tra bằng công cụ JSON thông thường.

## 4. Method pattern: chọn đúng method

Method pattern xác định code nào nhận directive. Cú pháp thường dùng:

```text
package/class.method(parameter_list)
```

Ví dụ:

| Pattern | Phạm vi khớp |
|---|---|
| `java/lang/String.indexOf()` | Method `indexOf` của `java.lang.String` |
| `Main.hotMethod` | Method `hotMethod` của class `Main` |
| `com/example/Service.*` | Các method trong class `Service` |
| `com/example/*.*` | Các class/method thuộc package pattern đó |
| `*.*` | Mọi method |

Dấu `*` là wildcard. Pattern càng rộng thì càng nhiều method có thể bị ảnh hưởng; vì vậy hãy ưu tiên pattern cụ thể.

Nếu bỏ chữ ký tham số, pattern có thể khớp nhiều overload cùng tên. Khi cần phân biệt overload, hãy ghi chữ ký theo dạng JVM method descriptor. Ví dụ method `long calculate(int)` có descriptor `(I)J`; pattern đầy đủ có thể viết `Main.calculate(I)J`.

Không nhầm method pattern với biểu thức regular expression. Wildcard `*` được diễn giải theo quy tắc method matching của HotSpot, không phải cú pháp regex tổng quát.

## 5. Các tùy chọn thường gặp

Tùy chọn directive có thể khác nhau giữa compiler và phiên bản JVM. Các option phổ biến gồm:

| Option | Tác dụng |
|---|---|
| `Enable` | Bật/tắt khả năng khớp và áp dụng directive |
| `Exclude` | Loại method khỏi compilation |
| `Log` | Giới hạn compilation log theo method khi dùng logging tương ứng |
| `PrintInlining` | In thông tin method nào được hoặc không được inline |
| `PrintCompilation` | In sự kiện biên dịch method |
| `PrintNMethods` | In thông tin nmethod được tạo |
| `PrintAssembly` | In assembly sau khi biên dịch nếu môi trường có disassembler phù hợp |
| `BackgroundCompilation` | Chọn compilation chạy nền hay foreground |
| `DisableIntrinsic` | Tắt intrinsic được chỉ định cho method phù hợp |
| `inline` | Chỉ định pattern method cần thử inline hoặc ngăn inline |

Một số option như `MaxNodeLimit`, `Vectorize` hoặc `BlockLayoutByFrequency` có phạm vi compiler riêng. Đừng sao chép một option từ bài viết cũ rồi giả định nó còn hợp lệ trên mọi JDK. Kiểm tra tài liệu JVM Guide và danh sách option của runtime hiện tại trước khi dùng.

### Điều khiển inlining

Inlining thay lời gọi method bằng phần thân method tại vị trí gọi nếu compiler quyết định việc đó có lợi. Trong directive, `inline` nhận các method pattern có tiền tố:

- `+` yêu cầu thử inline method khớp pattern.
- `-` yêu cầu không inline method khớp pattern.

Ví dụ:

```json
{
  "match": "com/example/Service.process",
  "c2": {
    "inline": [
      "-com/example/Service.normalize"
    ]
  }
}
```

Đây là chỉ thị cho compiler trong ngữ cảnh method `Service.process`. Việc yêu cầu inline không bảo đảm compiler luôn thực hiện được; giới hạn kích thước IR, tính chất method và các ràng buộc tối ưu vẫn có thể ngăn thao tác đó.

## 6. Nạp directive khi khởi động JVM

Tùy chọn `-XX:CompilerDirectivesFile` nạp directive file vào stack khi JVM khởi động. Đây là diagnostic option, nên cần mở khóa diagnostic options trước:

```bash
java \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:CompilerDirectivesFile=compiler-directives.json \
  -cp out Main
```

Để in directive stack khi khởi động:

```bash
java \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:+CompilerDirectivesPrint \
  -XX:CompilerDirectivesFile=compiler-directives.json \
  -cp out Main
```

Chỉ định một directive file ở command line; file đó có thể chứa nhiều block. Nếu file lỗi cú pháp hoặc directive không hợp lệ, JVM báo lỗi trong quá trình khởi động. Vì đây là tùy chọn HotSpot, JVM khác có thể không nhận các flag này.

## 7. Quản lý directive khi JVM đang chạy

HotSpot hỗ trợ thêm, gỡ và xem directive trong một process đang chạy bằng `jcmd`. Trước hết tìm PID:

```bash
jcmd
```

Sau đó có thể dùng các diagnostic command:

```bash
jcmd <pid> Compiler.directives_print
jcmd <pid> Compiler.directives_add compiler-directives.json
jcmd <pid> Compiler.directives_remove
jcmd <pid> Compiler.directives_clear
```

| Lệnh | Tác dụng |
|---|---|
| `Compiler.directives_print` | In directive stack hiện tại |
| `Compiler.directives_add file` | Thêm các directive trong file vào stack |
| `Compiler.directives_remove` | Gỡ directive đơn lẻ ở trên cùng stack |
| `Compiler.directives_clear` | Xóa các directive đã thêm khỏi stack |

`directives_remove` gỡ một directive ở trên cùng, không gỡ nguyên một file. `directives_clear` xóa các directive đã thêm bằng cơ chế này; directive mặc định của JVM vẫn tồn tại. Nếu file có lỗi, lệnh thêm directive báo lỗi và không thêm một phần cấu hình dở dang.

Việc thay đổi stack là thay đổi chính sách cho các quyết định compilation tiếp theo. Không nên hiểu rằng một directive mới tự động sửa ngay machine code đang được thread thực thi. Khi kiểm tra thay đổi runtime, hãy theo dõi compilation mới và trạng thái method bằng công cụ chẩn đoán.

## 8. Thứ tự ưu tiên và cách directive được áp dụng

Một method có thể khớp nhiều directive. HotSpot sử dụng directive phù hợp có ưu tiên cao nhất trong stack. Trong cùng một file, block ở đầu mảng có độ ưu tiên cao hơn block phía sau. Directive mặc định nằm ở cuối stack và khớp mọi method.

Khi dùng `Enable: false`, directive bị ẩn và không còn được dùng để khớp. Tùy chọn này có thể hữu ích khi nhiều block có phần cấu hình trùng nhau và cần tổ chức lại phạm vi áp dụng.

Compiler Control có thể dùng cùng `CompileCommand` và các cờ JVM cũ để tương thích. Khi các cấu hình xung đột, thứ tự ưu tiên là:

1. Compiler Control directives.
2. `CompileCommand`.
3. Các cờ command line liên quan.
4. Giá trị mặc định.

Nếu nhiều block có cùng option, cần kiểm tra thứ tự và phạm vi `c1`, `c2`, common block. Tránh đặt cùng một option ở nhiều vị trí nếu không có lý do rõ ràng; cấu hình trùng có thể làm người đọc khó biết giá trị nào có hiệu lực.

## 9. CompileCommand: cách điều khiển đơn giản hơn

`CompileCommand` là cơ chế HotSpot có trước Compiler Control. Nó vẫn được hỗ trợ vì tương thích ngược và hữu ích cho một vài lệnh đơn giản trên command line.

Ví dụ loại một method khỏi biên dịch:

```bash
java -XX:CompileCommand=exclude,Main.hotMethod -cp out Main
```

Một số command thường dùng:

- `exclude`: loại method khỏi compilation.
- `dontinline`: ngăn inline method.
- `inline`: thử inline method.
- `compileonly`: chỉ cho phép các method được chỉ định được biên dịch.
- `print`: in assembly sau khi biên dịch nếu môi trường hỗ trợ.
- `log`: điều khiển method được đưa vào compilation log.

Có thể truyền nhiều `-XX:CompileCommand` hoặc đưa lệnh vào file và chỉ định bằng `-XX:CompileCommandFile`. Nếu cần nhiều quy tắc, phân biệt C1/C2 hoặc quản lý directive ở runtime, Compiler Control có cấu trúc và khả năng kiểm soát tốt hơn. Không trộn hai cơ chế mà không hiểu độ ưu tiên của chúng.

## 10. Ví dụ Java 17: loại một method khỏi JIT bằng directive

Ví dụ sau gọi `hotMethod` nhiều lần để HotSpot có cơ hội biên dịch. Directive áp dụng cho đúng method này và loại nó khỏi cả C1 lẫn C2. Kết quả tính toán vẫn giống nhau; thay đổi quan sát được nằm ở compilation log.

**Main.java**

```java
public class Main {
    static long hotMethod(int seed) {
        long value = seed;
        for (int i = 0; i < 100; i++) {
            value = value * 31 + i;
        }
        return value;
    }

    public static void main(String[] args) {
        long checksum = 0;
        for (int i = 0; i < 100_000; i++) {
            checksum += hotMethod(i);
        }
        System.out.println("checksum=" + checksum);
    }
}
```

**compiler-directives.json**

```json
[
  {
    "match": "Main.hotMethod",
    "c1": {
      "Exclude": true
    },
    "c2": {
      "Exclude": true
    }
  }
]
```

Biên dịch:

```bash
javac --release 17 -Xlint:all -d out Main.java
```

Chạy không có directive:

```bash
java -XX:+PrintCompilation -cp out Main
```

Trên HotSpot, compilation log sẽ có các dòng cho `Main::hotMethod` khi method đạt ngưỡng biên dịch. Số thứ tự, compilation level và thời điểm xuất hiện có thể khác theo runtime và tải.

Chạy với directive:

```bash
java \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:CompilerDirectivesFile=compiler-directives.json \
  -XX:+CompilerDirectivesPrint \
  -XX:+PrintCompilation \
  -cp out Main
```

Trong log chẩn đoán, cần thấy directive `Main.hotMethod` với `Exclude:true` ở C1 và C2, cùng thông báo HotSpot loại method khỏi compilation. Không còn entry biên dịch thành công cho `Main::hotMethod` trong lần chạy được kiểm soát.

Dòng kết quả của chương trình:

```text
checksum=4175259435833549296
```

Checksum giống nhau giữa hai lần chạy vì directive điều khiển cách HotSpot biên dịch method, không thay đổi phép tính Java. Các dòng `PrintCompilation` và thông tin directive là log chẩn đoán; số thứ tự và nội dung phụ thuộc phiên bản JVM.

Ví dụ này đã được biên dịch bằng `javac --release 17 -Xlint:all` và chạy trên OpenJDK 24.0.2. Cả lần chạy mặc định và lần chạy có directive đều tạo cùng checksum; lần chạy mặc định biên dịch `Main::hotMethod`, còn lần chạy có directive hiển thị method bị loại khỏi compilation ở level C1 và C2.

## 11. Đo lường và kiểm chứng hiệu quả

Một directive được nạp thành công không đồng nghĩa nó cải thiện hiệu năng. Hãy kiểm tra cả việc directive được áp dụng lẫn tác động của nó lên ứng dụng:

- Dùng `-XX:+CompilerDirectivesPrint` hoặc `jcmd Compiler.directives_print` để xem directive stack.
- Dùng `-XX:+PrintCompilation` để quan sát sự kiện biên dịch.
- Dùng `PrintInlining` để xem quyết định inline ở compilation phù hợp.
- Dùng `-XX:+LogCompilation` khi cần file log compilation chi tiết; `Log` trong directive có thể giới hạn method được ghi.
- Dùng JFR, profiler hoặc JMH để đo CPU, latency, throughput và allocation trên workload đại diện.
- So sánh cùng dữ liệu, cùng JVM, cùng cấu hình GC và cùng điều kiện warm-up.

Không đánh giá một thay đổi chỉ từ thời gian chạy một lần. JIT chịu ảnh hưởng bởi warm-up, profile, tiered compilation, tải hệ thống và code cache. Một method bị loại khỏi compilation có thể chạy chậm hơn nhiều; ngăn inline có thể làm tăng call overhead; ép inline có thể làm code phình lớn và gây tác động ngược.

`PrintAssembly` cần thư viện disassembler phù hợp với nền tảng và bản dựng JVM. Nếu runtime không có thư viện đó, không giả định flag sẽ cung cấp assembly. Dùng các công cụ profiling và log phù hợp với môi trường thực tế.

## 12. Rủi ro và lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng pattern quá rộng | Nhiều method bị thay đổi quyết định JIT ngoài dự kiến | Dùng pattern hẹp và chữ ký cụ thể |
| Quên `UnlockDiagnosticVMOptions` | JVM từ chối diagnostic option hoặc directive file | Đặt `-XX:+UnlockDiagnosticVMOptions` trước directive flag |
| Directive JSON sai cú pháp | JVM báo lỗi khi nạp và có thể không khởi động | Kiểm tra JSON và chạy thử trên đúng JDK |
| Đặt option C2 trong block chung | Option có thể không có tác dụng với compiler mong muốn | Đặt option đúng trong `c1` hoặc `c2` |
| Coi `Exclude` là vô hiệu hóa method | Gây hiểu nhầm về hành vi chương trình | Method vẫn chạy; directive chỉ điều khiển compilation |
| Ép inline tùy tiện | Code phình lớn, compile lâu hoặc hiệu năng giảm | Chỉ thử với method đã đo và kiểm chứng |
| Nhầm directive mới sửa code đã biên dịch ngay lập tức | Đọc sai kết quả khi thử runtime update | Quan sát các compilation tiếp theo và trạng thái code thực tế |
| Kết luận hiệu năng từ một lần chạy | Kết quả bị nhiễu bởi warm-up và tải | Benchmark có lặp lại, warm-up và workload đại diện |
| Dùng flag HotSpot trên JVM khác | Flag có thể không tồn tại hoặc mang ý nghĩa khác | Xác nhận vendor và implementation của JVM |

Không nên dùng Compiler Control như một bộ tối ưu hóa thủ công cho toàn bộ ứng dụng. Hãy bắt đầu từ profile, xác định method có vấn đề, thử directive nhỏ nhất có thể, đo tác động rồi gỡ directive nếu không còn cần thiết. Directive phục vụ chẩn đoán hoặc workaround nên có lý do, phạm vi và điều kiện loại bỏ rõ ràng.

## 13. Checklist sử dụng Compiler Control

- JVM đang chạy có phải HotSpot/OpenJDK tương thích với các flag được dùng không?
- Method pattern có chọn đúng class, method và overload không?
- Directive đặt option trong common, C1 hay C2 đúng phạm vi chưa?
- Directive file có cú pháp hợp lệ và được nạp bằng `CompilerDirectivesFile` chưa?
- `UnlockDiagnosticVMOptions` đã được đặt trước diagnostic flag chưa?
- Thứ tự block và directive stack có tạo đúng độ ưu tiên không?
- Có kiểm tra bằng `CompilerDirectivesPrint`, `PrintCompilation` hoặc `jcmd` không?
- Kết quả ứng dụng có được giữ nguyên sau khi thay đổi compilation policy không?
- Hiệu năng có được đo bằng workload và benchmark đại diện không?
- Directive có được ghi lại mục đích và kế hoạch gỡ bỏ khi hết cần thiết không?

Compiler Control cho phép HotSpot áp dụng chính sách biên dịch JIT theo từng method bằng directive file hoặc diagnostic command lúc runtime. `match` chọn method; block `c1`, `c2` và common xác định phạm vi option; thứ tự directive quyết định quy tắc nào có ưu tiên. Hãy dùng Compiler Control để chẩn đoán hoặc thử nghiệm có kiểm soát, kiểm tra compilation log và đo workload thực tế trước khi giữ một directive trong môi trường chạy dài hạn.

## Tài liệu tham khảo

- [JEP 165: Compiler Control – Oracle JDK 9 What's New](https://docs.oracle.com/javase/9/whatsnew/)
- [Java Virtual Machine Guide, Release 25 – Compiler Control](https://docs.oracle.com/en/java/javase/25/vm/java-virtual-machine-guide.pdf)
- [The java Command, JDK 26 – CompileCommand và CompilerDirectivesFile](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
