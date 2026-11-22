# Giữ hợp đồng API nhất quán giữa các phần triển khai

Multi-release JAR (MR-JAR) cho phép một thư viện đóng gói **một implementation cơ sở** cùng các implementation thay thế dành cho những phiên bản Java mới hơn. Khi chạy, JVM chọn class phù hợp với phiên bản runtime. Vì vậy, cùng một thư viện có thể thực thi bằng những bytecode khác nhau trên các JDK khác nhau.

Dù implementation thay đổi, **hợp đồng API mà consumer nhìn thấy cần nhất quán giữa các phiên bản**. Một ứng dụng đã biên dịch với API cơ sở phải tiếp tục liên kết và nhận được hành vi đã cam kết khi chạy trên JDK chọn implementation trong `META-INF/versions/N`.

Điều này không có nghĩa các implementation phải dùng cùng thuật toán. Implementation mới có thể tận dụng API JDK mới, tối ưu hiệu năng hoặc thay đổi cách xử lý nội bộ, miễn là giữ nguyên chữ ký và hành vi mà thư viện công bố.

## 1. Multi-release JAR chọn implementation như thế nào?

Một MR-JAR có thể chứa class ở thư mục gốc và các bản thay thế theo phiên bản Java:

~~~text
codec.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/codec/MessageCodec.class
│       └── 21/
│           └── com/example/codec/MessageCodec.class
└── com/
    └── example/
        └── codec/
            └── MessageCodec.class
~~~

Manifest phải khai báo:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Quy tắc chọn class:

- JAR phải có thuộc tính manifest `Multi-Release: true`.
- Thư mục phiên bản nằm dưới `META-INF/versions/N`, trong đó `N` là số phiên bản Java từ 9 trở lên.
- Khi runtime cần một class, Java chọn entry versioned có số phiên bản cao nhất nhưng không vượt quá phiên bản runtime.
- Nếu không có entry phù hợp, Java dùng class ở thư mục gốc.
- Runtime không hỗ trợ cơ chế multi-release sẽ dùng class ở thư mục gốc và không xem các entry trong `META-INF/versions` là class thay thế.

Ví dụ nếu JAR có base, `versions/9` và `versions/21`:

| Runtime | Implementation được chọn |
|---|---|
| Java 9 đến 20 | `META-INF/versions/9` |
| Java 21 trở lên | `META-INF/versions/21` |

Nếu có thêm `versions/25`, runtime Java 25 trở lên sẽ ưu tiên bản 25. Các entry versioned phải tương ứng với đường dẫn logic của entry cơ sở mà chúng thay thế.

Nếu thiếu `Multi-Release: true`, thư mục `META-INF/versions` không được diễn giải như các implementation thay thế theo phiên bản.

## 2. Hợp đồng API cần giữ nhất quán gồm những gì?

Một hợp đồng API không chỉ là tên method. Consumer có thể phụ thuộc vào cấu trúc kiểu, quy tắc gọi và kết quả quan sát được.

### Binary compatibility

Bytecode đã biên dịch liên kết với tên class, tên method và descriptor của thành viên. Giữa base và versioned implementation, cần giữ ổn định:

- Tên đầy đủ và binary name của class/interface.
- Kiểu cha và các interface được triển khai.
- Constructor, method và field public/protected mà consumer được phép dùng.
- Tên method, kiểu tham số, kiểu trả về và descriptor JVM.
- Mức truy cập và các quan hệ kế thừa cần thiết.

Thay đổi method từ `public String encode(byte[] input)` thành `public byte[] encode(String input)` là thay đổi hợp đồng. Consumer cũ có thể gặp `NoSuchMethodError` hoặc lỗi liên kết tương tự khi runtime chọn class versioned không còn method mà bytecode đang gọi.

Giữ nguyên tên method nhưng thay đổi kiểu trả về cũng có thể làm thay đổi descriptor. Không coi việc hai method có tên giống nhau là đủ để bảo đảm tương thích nhị phân.

### Source compatibility

Consumer biên dịch lại còn phụ thuộc vào:

- Generic type, type bounds và kiểu trả về.
- Checked exception được khai báo.
- Visibility, overload và cách compiler chọn method.
- Annotation có ý nghĩa với compiler, framework hoặc công cụ sinh mã.
- Các kiểu public xuất hiện trong chữ ký API.

Một API có thể vẫn liên kết với bytecode cũ nhưng khiến mã nguồn consumer không biên dịch được sau khi nâng cấp. Vì vậy, kiểm tra binary compatibility chưa thay thế hoàn toàn kiểm tra source compatibility.

### Behavioral compatibility

Các implementation cần tuân theo cùng một hành vi đã công bố:

- Điều kiện đầu vào và điều kiện đầu ra.
- Cách xử lý `null`, dữ liệu rỗng và dữ liệu biên.
- Loại exception và điều kiện phát sinh exception.
- Thứ tự kết quả, quy tắc so sánh, encoding và chuẩn hóa dữ liệu.
- Mutability, thread-safety và side effect.
- Quyền sở hữu, đóng và giải phóng tài nguyên.
- Quy tắc locale, timezone hoặc charset nếu API có liên quan.

Ví dụ, nếu API cam kết ném `NullPointerException` khi nhận `null`, implementation Java 21 không nên âm thầm trả về `false` chỉ vì dùng một API JDK mới có cách xử lý khác.

### Module và service contract

Với modular JAR, hợp đồng còn có thể bao gồm:

- Tên module.
- Các package được `exports`.
- Các dependency `requires` cần thiết.
- Các service được khai báo bằng `uses` và `provides`.
- Package được mở cho reflection khi framework cần truy cập sâu.

Một `module-info.class` versioned có thể được đặt trong `META-INF/versions/9`. Nếu descriptor thay đổi giữa các runtime, consumer có thể đọc được package hoặc service khác nhau. Chỉ thay đổi descriptor theo phiên bản khi đó là chủ đích và được kiểm thử như một phần của hợp đồng phân phối.

## 3. Điều gì được phép khác nhau giữa các implementation?

Implementation có thể thay đổi nội bộ mà không làm consumer phải sửa mã:

- Thuật toán, cấu trúc dữ liệu hoặc cách cache.
- Sử dụng API JDK mới hơn trong class versioned.
- Cách tối ưu vòng lặp, xử lý chuỗi hoặc I/O.
- Cách tổ chức helper private/package-private.
- Chiến lược đồng bộ nội bộ, miễn vẫn giữ cam kết thread-safety.
- Tối ưu bộ nhớ hoặc hiệu năng mà không đổi kết quả được cam kết.

Không nên để implementation mới:

- Xóa hoặc đổi chữ ký public/protected mà consumer cũ sử dụng.
- Thay đổi kiểu dữ liệu xuất hiện trong public API thành kiểu chỉ có trên JDK mới.
- Đổi quy tắc `null`, exception, encoding hoặc kết quả.
- Làm khác thứ tự, mutability hay side effect đã được công bố.
- Yêu cầu dependency mới nhưng lại để dependency đó xuất hiện trong đường chạy base.
- Tạo ra API công khai chỉ có ở runtime mới mà không mô tả rõ tính phụ thuộc phiên bản.

Nếu một API thực sự chỉ có trên Java 21 trở lên, hãy coi đó là API phụ thuộc runtime có chủ đích và ghi rõ yêu cầu phiên bản. Với thư viện cần một hợp đồng chung cho mọi runtime được hỗ trợ, giữ public API giống nhau ở tất cả các implementation.

## 4. Ví dụ: giữ cùng API giữa base Java 17 và Java 21

Ví dụ dùng class `MessageCodec` với một method public:

~~~java
public static boolean isBlank(String input)
~~~

Hợp đồng được công bố:

- `input` không được là `null`; nếu là `null`, method ném `NullPointerException`.
- Trả về `true` khi chuỗi rỗng hoặc mọi code point đều thỏa `Character.isWhitespace` trên JDK đang chạy.
- Trả về `false` khi có ít nhất một code point không phải whitespace.
- Không thay đổi chuỗi đầu vào.

Base implementation được biên dịch cho Java 17 và duyệt từng code point:

~~~java
// src/base/com/example/codec/MessageCodec.java
package com.example.codec;

import java.util.Objects;

public final class MessageCodec {
    private MessageCodec() {
    }

    public static boolean isBlank(String input) {
        Objects.requireNonNull(input, "input");

        for (int offset = 0; offset < input.length();) {
            int codePoint = input.codePointAt(offset);

            if (!Character.isWhitespace(codePoint)) {
                return false;
            }

            offset += Character.charCount(codePoint);
        }

        return true;
    }

    // Chỉ phục vụ ví dụ để nhận diện implementation đang được chọn.
    // Đây không phải public API.
    static String implementationId() {
        return "base-java17";
    }
}
~~~

Implementation dành cho Java 21 dùng `String.isBlank()`, một API có từ Java 11:

~~~java
// src/java21/com/example/codec/MessageCodec.java
package com.example.codec;

import java.util.Objects;

public final class MessageCodec {
    private MessageCodec() {
    }

    public static boolean isBlank(String input) {
        Objects.requireNonNull(input, "input");
        return input.isBlank();
    }

    // Chữ ký package-private giữ nguyên; nội dung chỉ để kiểm tra demo.
    static String implementationId() {
        return "java21";
    }
}
~~~

Hai implementation dùng cách viết khác nhau nhưng giữ cùng public method, cùng quy tắc null và cùng định nghĩa whitespace theo `Character.isWhitespace` của runtime. Cả hai đều trả về cùng kết quả cho cùng đầu vào trên cùng một JDK.

Vì hợp đồng này dựa trên bảng ký tự Unicode của JDK, nếu thư viện cần kết quả cố định tuyệt đối giữa các thế hệ Unicode, hãy định nghĩa rõ tập code point trong hợp đồng và dùng cùng predicate đó ở mọi implementation.

Method `implementationId()` chỉ để minh họa runtime đã chọn class nào. Nó là package-private và không thuộc public API mà consumer bên ngoài sử dụng.

## 5. Đóng gói thành multi-release JAR

Cấu trúc source và output:

~~~text
project/
├── src/
│   ├── base/
│   │   └── com/example/codec/MessageCodec.java
│   ├── java21/
│   │   └── com/example/codec/MessageCodec.java
│   └── main/
│       └── com/example/codec/Main.java
└── build/
    ├── classes/
    │   ├── base/
    │   └── java21/
    └── MANIFEST.MF
~~~

Class `Main` được biên dịch cùng base implementation. Nó gọi public API và method chẩn đoán package-private để in ra implementation đang được dùng:

~~~java
// src/main/com/example/codec/Main.java
package com.example.codec;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("implementation=" + MessageCodec.implementationId());
        System.out.println("empty=" + MessageCodec.isBlank(""));
        System.out.println("space-and-tab=" + MessageCodec.isBlank(" \t"));
        System.out.println("non-breaking-space=" + MessageCodec.isBlank("\u00A0"));
        System.out.println("text=" + MessageCodec.isBlank("java"));

        try {
            MessageCodec.isBlank(null);
            throw new AssertionError("null should be rejected");
        } catch (NullPointerException expected) {
            System.out.println("null-contract=NullPointerException");
        }
    }
}
~~~

Biên dịch base class và main class với release 17:

~~~powershell
New-Item -ItemType Directory -Force build/classes/base, build/classes/java21 | Out-Null
javac --release 17 -d build/classes/base src/base/com/example/codec/MessageCodec.java src/main/com/example/codec/Main.java
~~~

Biên dịch implementation Java 21 riêng:

~~~powershell
javac --release 21 -d build/classes/java21 src/java21/com/example/codec/MessageCodec.java
~~~

Tạo file `build/MANIFEST.MF` với nội dung:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Đóng gói base class ở gốc JAR và thêm implementation Java 21 vào đúng thư mục versioned:

~~~powershell
jar --create --file build/codec.jar --manifest build/MANIFEST.MF -C build/classes/base . --release 21 -C build/classes/java21 .
~~~

Kiểm tra cấu trúc:

~~~powershell
jar --list --file build/codec.jar
~~~

Các entry quan trọng:

~~~text
META-INF/MANIFEST.MF
com/example/codec/MessageCodec.class
com/example/codec/Main.class
META-INF/versions/21/com/example/codec/MessageCodec.class
~~~

Trên JDK có hỗ trợ lệnh kiểm tra MR-JAR, có thể chạy:

~~~powershell
jar --validate --file build/codec.jar
~~~

Lệnh này giúp phát hiện một số lỗi cấu trúc của multi-release JAR. Nó không thay thế kiểm thử API và hành vi giữa các implementation.

## 6. Chạy và xác nhận implementation được chọn

Chạy trên Java 21 trở lên:

~~~powershell
java -cp build/codec.jar com.example.codec.Main
~~~

Runtime chọn class tại `META-INF/versions/21`. Stdout:

~~~text
implementation=java21
empty=true
space-and-tab=true
non-breaking-space=false
text=false
null-contract=NullPointerException
~~~

Trên Java 17 đến 20, JAR không có entry versioned phù hợp nên runtime dùng base implementation.

Để kiểm tra base implementation độc lập, tạo một JAR chỉ chứa base class và manifest thông thường, không có `Multi-Release: true`:

~~~powershell
jar --create --file build/codec-base.jar -C build/classes/base .
java -cp build/codec-base.jar com.example.codec.Main
~~~

Stdout của base-only JAR:

~~~text
implementation=base-java17
empty=true
space-and-tab=true
non-breaking-space=false
text=false
null-contract=NullPointerException
~~~

Hai dòng `implementation` khác nhau vì runtime chọn implementation khác nhau. Các kết quả public API còn lại giống nhau. Đây là điều cần đạt: consumer quan sát được cùng hợp đồng dù bytecode thực thi khác nhau.

## 7. So sánh public API của các class versioned

Có thể dùng `javap -public` để xem public surface của base và implementation mới:

~~~powershell
javap -public -classpath build/classes/base com.example.codec.MessageCodec
javap -public -classpath build/classes/java21 com.example.codec.MessageCodec
~~~

Cả hai phải cho cùng chữ ký public:

~~~text
public final class com.example.codec.MessageCodec {
  public static boolean isBlank(java.lang.String);
}
~~~

`javap -public` là phép kiểm tra nhanh. Với thư viện phát hành cho nhiều consumer, nên bổ sung công cụ kiểm tra binary API compatibility như japicmp hoặc Revapi và lưu kết quả trong CI.

Không chỉ so sánh tên method. Cần kiểm tra cả descriptor, kiểu trả về, visibility, generic signature, hierarchy, checked exception và các thành viên public/protected được công bố.

## 8. Kiểm thử cùng một contract suite trên mọi implementation

Một bộ contract test nên được dùng lại cho base và tất cả implementation versioned. Không tạo test riêng chỉ kiểm tra code path của một phiên bản rồi bỏ qua các bản còn lại.

Với ví dụ `isBlank`, test tối thiểu nên xác nhận:

| Trường hợp | Kết quả theo hợp đồng |
|---|---|
| Chuỗi rỗng | `true` |
| Chỉ có space/tab/newline | `true` |
| Chứa chữ hoặc số | `false` |
| Chứa non-breaking space U+00A0 | `false` theo `Character.isWhitespace` |
| Đầu vào `null` | `NullPointerException` |

Trong CI, chạy cùng test suite với:

- JAR base-only để kiểm tra implementation cơ sở.
- MR-JAR trên phiên bản Java thấp nhất được hỗ trợ.
- MR-JAR trên từng runtime có versioned implementation, đặc biệt tại các mốc thư mục `META-INF/versions/N`.
- JDK mới nhất mà dự án tuyên bố hỗ trợ.

Khi thêm một implementation mới ở `versions/25`, cần chạy lại contract suite trên Java 25 trở lên để xác nhận bản 25 không làm thay đổi kết quả đã cam kết.

Ngoài test giá trị trả về, kiểm tra thêm exception, null, edge case, thứ tự, thread-safety, mutability, resource lifecycle, service loading và reflection nếu chúng thuộc hợp đồng thư viện.

## 9. Những lỗi thường gặp khi giữ API giữa các version

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Base có method public nhưng versioned class xóa method đó | Consumer đã biên dịch có thể gặp lỗi liên kết | Giữ cùng public/protected signature ở mọi class thay thế |
| Versioned class đổi kiểu tham số hoặc trả về | Binary descriptor không còn khớp | Kiểm tra descriptor và API diff trước khi đóng gói |
| Implementation mới xử lý `null` khác base | Cùng API nhưng hành vi khác theo JDK | Định nghĩa rõ null contract và chạy cùng test suite |
| Base và versioned khác loại exception | Consumer phải xử lý khác nhau tùy runtime | Giữ loại exception và điều kiện ném như hợp đồng |
| Versioned class đưa kiểu JDK mới vào public signature | Consumer hoặc runtime cũ không thể dùng API đó | Giữ kiểu mới trong implementation nội bộ hoặc công bố rõ yêu cầu runtime |
| Chỉ test trên JDK mới nhất | Bỏ sót lỗi ở base hoặc version boundary | Test base-only và từng runtime được hỗ trợ |
| Quên `Multi-Release: true` | Runtime không chọn versioned class | Kiểm tra manifest và entry trong JAR |
| Đặt class sai thư mục version | Runtime không tìm thấy implementation thay thế | Dùng `META-INF/versions/N` với N từ 9 trở lên và đúng đường dẫn package |
| Versioned module descriptor đổi exports/service ngoài ý muốn | Khả năng đọc hoặc service discovery thay đổi giữa runtime | Kiểm tra module descriptor theo từng phiên bản |
| Chỉ so sánh public method name | Bỏ sót descriptor, generic, exception hoặc hierarchy | Dùng API diff tool và contract tests |

## 10. Quy trình duy trì hợp đồng API

Khi thêm hoặc sửa implementation versioned, thực hiện theo trình tự:

1. Viết rõ public contract trước khi tối ưu implementation: chữ ký, input, output, exception, null, thread-safety và side effect.
2. Giữ base implementation tương thích với runtime thấp nhất được hỗ trợ.
3. Chỉ thêm class versioned khi có lý do sử dụng API hoặc tối ưu của JDK mới.
4. Giữ cùng binary name và public API giữa base và versioned class thay thế.
5. Không để public signature của bản mới phụ thuộc vào kiểu chỉ tồn tại ở runtime cao hơn, trừ khi chủ đích công bố API riêng theo phiên bản.
6. Chạy cùng contract suite với base-only JAR và MR-JAR trên các runtime mục tiêu.
7. So sánh API bằng `javap` hoặc công cụ binary compatibility.
8. Kiểm tra manifest, đường dẫn versioned và cấu trúc JAR.
9. Kiểm tra module descriptor và service contract nếu JAR là modular.
10. Phát hành artifact sau khi mọi runtime được hỗ trợ đều đáp ứng cùng hợp đồng đã công bố.

Multi-release JAR cho phép một thư viện thay đổi implementation theo JDK mà không bắt consumer phải thay đổi cách sử dụng. Giữ chữ ký, module contract và hành vi công khai nhất quán giúp các bản implementation khác nhau vẫn là những cách thực thi của cùng một API.
