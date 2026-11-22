# Kiểm thử dominance bằng compile failure trong Java Pattern Matching

**Dominance** trong `switch` có pattern là quan hệ giữa các nhánh `case`: nếu một nhánh xuất hiện trước đã bao phủ mọi trường hợp mà nhánh sau có thể khớp, nhánh sau bị **dominated**. Với những trường hợp được Java quy định, compiler **từ chối biên dịch** thay vì để một nhánh thừa nằm im trong chương trình. Có thể biến đặc tính này thành một phép thử có chủ đích: **đưa cho compiler một đoạn code cố ý sai, khẳng định nó phải bị từ chối vì đúng lý do dominance**. Đó là **negative compilation test** hay **compile-failure test**.

Bài học thuộc **Java Core Pattern Matching → Kiểm thử**, tập trung vào cách viết negative tests cho *dominated case labels*, kiểm tra lại khi refactor thứ tự `case` hoặc guard `when`, dùng `javac` và Java Compiler API để tự động hóa, và phân biệt lỗi dominance với các loại lỗi biên dịch khác.

**Yêu cầu phiên bản:** Sử dụng cú pháp đã hoàn thiện từ **Java 21**: pattern matching for `switch` (JEP 441) và record patterns (JEP 440). Các ví dụ chạy với JDK 21+ bằng `--release 21`, không cần `--enable-preview`.

## 1. Dominance là gì và vì sao kiểm thử nó?

Xem `switch expression` trên một biến có kiểu `Object`:

~~~java
// CỐ Ý SAI — trích đoạn trong phương thức, input có kiểu Object.
String result = switch (input) {
    case CharSequence text -> "Any CharSequence";
    case String text -> "A String";
    case null -> "Null";
    default -> "Other";
};
~~~

`String` triển khai `CharSequence`. Vì vậy mọi `String` đều đã khớp `case CharSequence text` trước đó; nhánh `case String text` không còn cơ hội được chọn. Compiler có thể báo thông điệp dạng **"this case label is dominated by a preceding case label"** (câu chữ cụ thể thay đổi theo JDK).

Sửa đúng thứ tự:

~~~java
// HỢP LỆ với Java 21+.
String result = switch (input) {
    case String text -> "A String";
    case CharSequence text -> "Any CharSequence";
    case null -> "Null";
    default -> "Other";
};
~~~

Nhánh **cụ thể trước, tổng quát sau**. Giá trị kiểu `String` vào nhánh đầu; những kiểu `CharSequence` khác đi tới nhánh sau.

Dominance không đơn thuần là một cảnh báo về code style. Trong những trường hợp được ngôn ngữ quy định, đó là **lỗi compile-time**. Nếu vô tình thay đổi thứ tự case trong quá trình refactor, compiler giúp ngăn nhánh không thể tới được. Compile-failure test giúp *ghi lại* những ví dụ sai quan trọng như một phần của tài liệu và bộ kiểm thử ngôn ngữ của dự án.

### Phân biệt ba loại kiểm tra

| Loại kiểm tra | Câu hỏi | Kết quả mong đợi |
| --- | --- | --- |
| **Compile-success test** | Mẫu đúng có biên dịch không? | Compiler chấp nhận |
| **Compile-failure test** | Mẫu sai có bị compiler từ chối đúng lý do không? | Compiler trả trạng thái thất bại và có chẩn đoán thích hợp |
| **Runtime behavior test** | Mẫu đã biên dịch phân loại giá trị đúng không? | Chạy code và đối chiếu output/exception |

Không nên coi một test “compile fail” là đủ chỉ vì nó bất ngờ lỗi ở một chỗ khác. Nếu đoạn mã sai chính tả tên lớp và không compile, điều đó **không chứng minh** compiler đã phát hiện dominance. Negative tests cần xác nhận **nguyên nhân từ chối**.

## 2. Kiểm thử dominance giữa kiểu cha và kiểu con

Đây là ví dụ cơ bản và dễ giải thích nhất cho người mới học pattern matching:

~~~java
// File: DominanceCase.java
// CỐ Ý SAI: chương trình này phải bị compiler từ chối.
public class DominanceCase {
    static String classify(Object input) {
        return switch (input) {
            case CharSequence text -> "text-like";
            case String text -> "string";
            case null -> "null";
            default -> "other";
        };
    }
}
~~~

Chạy bằng JDK 21+:

~~~bash
javac --release 21 DominanceCase.java
~~~

**Kết quả mong đợi:** `javac` trả **mã thoát khác 0**, có lỗi dominance tại nhánh `case String text`; **không sinh bản build hợp lệ** cho ví dụ này. Tùy phiên bản và cách cấu hình, thông báo hiển thị có thể khác nhau. Không nên hard-code nguyên văn toàn bộ thông báo lỗi tiếng Anh nếu không kiểm soát phiên bản compiler.

Vì `String` là subtype của `CharSequence`, nhánh thứ hai bị che. Vấn đề này **khác** với việc dùng lại tên pattern variable `text`: tên có thể được khai báo riêng ở các case khác nhau; lỗi nằm ở **quan hệ bao phủ kiểu**.

### Case kiểu `Object` cũng có thể quá rộng

~~~java
// CỐ Ý SAI, trích đoạn.
String kind = switch (input) {
    case Object any -> "some object";
    case Integer n -> "integer"; // Nhánh Integer đã bị che.
};
~~~

Với selector kiểu `Object`, pattern tổng quát `Object any` bao phủ mọi `Integer` không null. Đừng dùng một type pattern rộng ở đầu rồi mong các subtype phía sau được chọn. Đối với `null`, cần xem chính sách riêng; type pattern không thay thế cách xử lý null tùy ý.

**Điểm kiểm thử:** chọn cặp có quan hệ subtype rõ ràng, ví dụ `CharSequence`/`String`, để negative test chỉ kiểm tra một quy tắc. Đừng đồng thời thêm lỗi thiếu biến, sai kiểu trả về hoặc thiếu khả năng bao phủ, vì có thể che nguyên nhân test cần xác nhận.

## 3. Kiểm thử dominance giữa case có guard và không guard

Với `when`, pattern có thể được bổ sung điều kiện Boolean. Một case **không guard** đứng trước thường bao phủ case có guard cùng pattern:

~~~java
// CỐ Ý SAI — input là Object.
String label = switch (input) {
    case String value -> "some string";
    case String value when value.isBlank() -> "blank";
    case null -> "null";
    default -> "other";
};
~~~

Mọi `String` trắng vẫn là một `String`; nhánh đầu đã nhận tất cả `String`. Nhánh có `when` ở sau bị dominated, và ví dụ phải **không biên dịch**.

Sửa bằng cách đặt trường hợp đặc biệt trước:

~~~java
// HỢP LỆ với Java 21+.
String label = switch (input) {
    case String value when value.isBlank() -> "blank";
    case String value -> "some string";
    case null -> "null";
    default -> "other";
};
~~~

Cách đọc tương đương với:

~~~java
// Trích đoạn tương đương về ý tưởng kiểm tra type/blank, input là Object.
if (input instanceof String value && value.isBlank()) {
    return "blank";
}
if (input instanceof String value) {
    return "some string";
}
if (input == null) {
    return "null";
}
return "other";
~~~

Đoạn `if` trên chỉ minh họa trong **phương thức trả về `String`**. Trong `switch`, compiler thực hiện kiểm tra quan hệ giữa các case pattern; ở đây không cần tự chứng minh nhánh thứ hai có thể chạy hay không.

### Guard trả `false` không phải dominance

Nếu `value` là chuỗi `"Java"`, guard `value.isBlank()` sai, nên case đầu không được chọn. Java tiếp tục đến `case String value` và trả `"some string"`. Đây là đường chạy hợp lệ. Dominance chỉ xảy ra nếu **một nhánh trước đã bao phủ hoàn toàn nhánh sau** theo các quy tắc ngôn ngữ áp dụng.

## 4. Kiểm thử dominance với record pattern

Record pattern cho phép phân rã component của một record. Khi một case khớp mọi giá trị thuộc record, nhánh có guard chuyên biệt cùng record đặt phía sau cũng bị che:

~~~java
// CỐ Ý SAI — các khai báo nằm trong lớp/phạm vi hợp lệ.
record Point(int x, int y) {}

String label = switch (input) {
    case Point(var x, var y) -> "any point";
    case Point(var x, var y) when x == 0 -> "on vertical axis";
    case null -> "null";
    default -> "other";
};
~~~

Với kiểu `Point`, cả hai component `int` đều khớp `var` tương ứng; nhánh đầu là nhánh tổng quát cho tất cả `Point`. Nhánh `when x == 0` không còn được chọn. Đây là một test dominance nên có trong module dạy **record patterns + switch**.

Sửa:

~~~java
// HỢP LỆ; input là Object, Point đã được khai báo.
String label = switch (input) {
    case Point(var x, var y) when x == 0 -> "on vertical axis";
    case Point(var x, var y) -> "other point";
    case null -> "null";
    default -> "other";
};
~~~

**Thận trọng khi mở rộng ví dụ:** record pattern có component là kiểu tham chiếu có thể có quy tắc khớp `null` khác với `var`. Khi thử dominance giữa các record patterns phức tạp, nên tách riêng test về kiểu/component, tránh nhầm lỗi dominance với một ràng buộc hình dạng hay kiểu record không hợp lệ.

## 5. Compiler không chứng minh mọi quan hệ logic giữa các guard

Một điều dễ hiểu nhầm: “Nếu một guard có điều kiện rộng hơn guard sau, compiler chắc chắn phát hiện dominance”. Điều này **không đúng tổng quát** cho các biểu thức Boolean tùy ý.

Ví dụ:

~~~java
// Java 21+: trích đoạn HỢP LỆ VỀ MẶT BIÊN DỊCH.
String bucket = switch (input) {
    case String s when s.length() > 3 -> "more than 3";
    case String s when s.length() > 5 -> "more than 5";
    case String s -> "short";
    case null -> "null";
    default -> "other";
};
~~~

Về toán học, `s.length() > 5` kéo theo `s.length() > 3`. Với chuỗi độ dài 6, nhánh đầu đã trả `"more than 3"`, nên nhánh thứ hai không được chọn. Tuy nhiên, compiler Java **không giải quyết mọi suy luận logic giữa các guard**; đoạn trên vẫn có thể **biên dịch thành công** dù về ý nghĩa nghiệp vụ, nhánh `"more than 5"` không bao giờ nhận được chuỗi phù hợp.

Để phân loại đúng ý định, có thể đảo thứ tự:

~~~java
String bucket = switch (input) {
    case String s when s.length() > 5 -> "more than 5";
    case String s when s.length() > 3 -> "more than 3";
    case String s -> "short";
    case null -> "null";
    default -> "other";
};
~~~

**Bài học kiểm thử:** Một compile-failure test chỉ nên kỳ vọng lỗi khi Java **quy định compiler phải báo lỗi dominance**. Những guard có quan hệ nghiệp vụ phức tạp, giao nhau hoặc ngụ ý nhau cần **runtime tests, boundary tests** và review logic; compiler không thay thế những công cụ đó.

## 6. Cách thử thủ công bằng `javac`

Quy trình nhỏ nhất để kiểm tra một negative example:

1. Tạo tệp nguồn **chỉ chứa một lỗi dominance có chủ đích** như `DominanceCase.java` ở phần 2.
2. Dùng đúng `javac` và cờ `--release 21`.
3. Chạy biên dịch và quan sát **exit code thất bại**; không gọi thất bại này là “test đỏ” nếu đây là negative test đang mong đợi lỗi.
4. Kiểm tra chẩn đoán có nhắc tới dominated case (hoặc mã chẩn đoán thích hợp của compiler đang dùng), chứ không phải một lỗi cú pháp/thiếu class khác.
5. Đổi thứ tự case để tạo bản **positive control**, biên dịch lại và xác nhận thành công.

Trên shell POSIX (Bash, zsh), có thể sử dụng:

~~~bash
javac --release 21 DominanceCase.java
status=$?
if [ "$status" -eq 0 ]; then
  echo "FAIL: expected javac to reject the source"
  exit 1
fi
echo "javac rejected the source; inspect diagnostics for dominance"
~~~

Đoạn shell trên chỉ kiểm tra `exit code`; dòng cuối cố ý nhắc phải **kiểm tra nguyên nhân lỗi**. Đây là ví dụ minh họa, không phải bộ test hoàn chỉnh.

Trên PowerShell:

~~~powershell
javac --release 21 DominanceCase.java
if ($LASTEXITCODE -eq 0) {
    throw "FAIL: expected compilation to be rejected"
}
Write-Output "javac rejected the source; check dominance diagnostics"
~~~

Tương tự, `$LASTEXITCODE` chỉ nói biên dịch thất bại, không tự chứng minh đó là dominance. Để kiểm tra tự động và tránh lệ thuộc vào đường dẫn file tạm, có thể dùng **Java Compiler API (`javax.tools`)**.

### Không làm hỏng build chính bằng ví dụ cố ý sai

Một tệp `DominanceCase.java` cố ý chứa lỗi **không** được đưa vào tập source chính đang biên dịch của ứng dụng. Nếu làm thế, build luôn thất bại và CI không phân biệt được đây là negative test mong đợi hay lỗi thật. Hãy đặt negative examples trong tài nguyên kiểm thử riêng và dùng test harness chỉ định rõ **compiler nào** phải chạy trên mỗi snippet.

## 7. Tự động hóa negative tests bằng Java Compiler API (không tạo file nguồn)

Java cung cấp `ToolProvider.getSystemJavaCompiler()` và `DiagnosticCollector` để gọi trình biên dịch từ code Java. Có thể viết một harness nhận chuỗi source, biên dịch trong bộ nhớ rồi kiểm tra kết quả:

- Với **negative case**: `compiled == false` và có chẩn đoán thuộc loại dominance.
- Với **positive control**: `compiled == true`.
- Với một case khác cố ý sai cú pháp: chỉ `compiled == false` là **chưa đủ** để cho rằng test dominance đạt.

Ví dụ hoàn chỉnh sau dùng Java Compiler API, `SimpleJavaFileObject` và một `ForwardingJavaFileManager` giữ cả **input và output ở bộ nhớ**. Nhờ vậy, các positive snippets có thể được biên dịch mà không tạo `Sample.class` trong thư mục dự án.

### Chương trình tự động: `DominanceCompileTest.java`

~~~java
public class DominanceCompileTest {
    private record Outcome(boolean compiled, boolean dominated, String errors) {}

    private static Outcome compile(String source) {
        javax.tools.JavaCompiler compiler = javax.tools.ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A full JDK is required");
        }

        var diagnostics = new javax.tools.DiagnosticCollector<
                javax.tools.JavaFileObject>();

        var file = new javax.tools.SimpleJavaFileObject(
                java.net.URI.create("string:///Sample.java"),
                javax.tools.JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return source;
            }
        };

        try (var standard = compiler.getStandardFileManager(
                diagnostics, java.util.Locale.ROOT,
                java.nio.charset.StandardCharsets.UTF_8)) {
            var memory = new javax.tools.ForwardingJavaFileManager<
                    javax.tools.StandardJavaFileManager>(standard) {
                @Override
                public javax.tools.JavaFileObject getJavaFileForOutput(
                        Location location, String className,
                        javax.tools.JavaFileObject.Kind kind,
                        javax.tools.FileObject sibling) {
                    return new javax.tools.SimpleJavaFileObject(
                            java.net.URI.create("mem:///"
                                    + className.replace('.', '/') + kind.extension),
                            kind) {
                        @Override
                        public java.io.OutputStream openOutputStream() {
                            return new java.io.ByteArrayOutputStream();
                        }
                    };
                }
            };

            boolean compiled = Boolean.TRUE.equals(compiler.getTask(
                    null, memory, diagnostics,
                    java.util.List.of("--release", "21", "-proc:none"),
                    null, java.util.List.of(file)).call());

            boolean dominated = diagnostics.getDiagnostics().stream()
                    .anyMatch(d ->
                            d.getKind() == javax.tools.Diagnostic.Kind.ERROR
                            && d.getCode().contains("dominated"));

            String errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == javax.tools.Diagnostic.Kind.ERROR)
                    .map(d -> d.getCode()).distinct()
                    .reduce((a, b) -> a + "," + b).orElse("none");

            return new Outcome(compiled, dominated, errors);
        } catch (java.io.IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    }

    static void mustBeDominated(String name, String source) {
        Outcome out = compile(source);
        if (out.compiled() || !out.dominated()) {
            throw new AssertionError(
                    name + ": expected dominance, found " + out);
        }
        System.out.println(name + ": rejected for dominance");
    }

    static void mustCompile(String name, String source) {
        Outcome out = compile(source);
        if (!out.compiled()) {
            throw new AssertionError(
                    name + ": expected success, found " + out);
        }
        System.out.println(name + ": compiled");
    }

    public static void main(String[] args) {
        mustBeDominated("type hierarchy", """
                public class Sample {
                    static String classify(Object input) {
                        return switch (input) {
                            case CharSequence cs -> "char sequence";
                            case String s -> "string";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);

        mustBeDominated("guard order", """
                public class Sample {
                    static String classify(Object input) {
                        return switch (input) {
                            case String s -> "any string";
                            case String s when s.isBlank() -> "blank";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);

        mustBeDominated("record pattern", """
                public class Sample {
                    record Point(int x, int y) {}
                    static String classify(Object input) {
                        return switch (input) {
                            case Point(var x, var y) -> "point";
                            case Point(var x, var y) when x == 0 -> "x zero";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);

        mustCompile("valid specificity", """
                public class Sample {
                    static String classify(Object input) {
                        return switch (input) {
                            case String s when s.isBlank() -> "blank";
                            case String s -> "string";
                            case CharSequence cs -> "other text";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);

        mustCompile("overlapping guards", """
                public class Sample {
                    static String classify(Object input) {
                        return switch (input) {
                            case String s when s.length() > 3 -> "length > 3";
                            case String s when s.length() > 5 -> "length > 5";
                            case String s -> "short";
                            case null -> "null";
                            default -> "other";
                        };
                    }
                }
                """);
    }
}
~~~

Biên dịch và chạy harness bằng **JDK 21+**, không cần JUnit:

~~~bash
javac --release 21 -encoding UTF-8 DominanceCompileTest.java
java DominanceCompileTest
~~~

Đầu ra mong đợi:

~~~text
type hierarchy: rejected for dominance
guard order: rejected for dominance
record pattern: rejected for dominance
valid specificity: compiled
overlapping guards: compiled
~~~

**Chú ý:** hai dòng `overlapping guards: compiled` và `valid specificity: compiled` chỉ nói rằng compiler chấp nhận các đoạn source; chúng **không xác nhận logic phân loại runtime đúng**. Trường hợp overlapping guards được giữ lại có chủ đích để thể hiện giới hạn của compile-time dominance checking.

### Giải thích harness theo từng bước

**Bước 1 — Biểu diễn source bằng chuỗi.** Các Java text blocks `""" ... """` chứa một lớp `Sample` cho mỗi kiểm thử. Từng lần gọi compiler nhận **một chuỗi độc lập**, vì vậy có thể sử dụng cùng tên lớp `Sample` mà không xung đột giữa các test.

**Bước 2 — Dùng compiler của JDK hiện tại.** `ToolProvider.getSystemJavaCompiler()` chỉ có khi môi trường cung cấp compiler, thường là một JDK đầy đủ. `--release 21` yêu cầu biên dịch theo phiên bản ngôn ngữ và API được hỗ trợ cho Java 21. Cần chạy harness bằng JDK 21+ hỗ trợ release tương ứng.

**Bước 3 — Thu chẩn đoán.** `DiagnosticCollector` giữ các diagnostic mà không cần phân tích text được in ra console. Với các phiên bản `javac` được thử trong bài, mã diagnostic về dominance có chứa chuỗi `dominated`.

**Bước 4 — Không ghi class file kiểm thử ra disk.** `ForwardingJavaFileManager` trả `JavaFileObject` có `OutputStream` ghi vào `ByteArrayOutputStream`. Đây là cách tối giản để kiểm tra tính biên dịch mà không cần tạo tài nguyên đầu ra trên hệ thống file.

**Bước 5 — Đối chiếu kết quả.** `mustBeDominated` yêu cầu vừa **biên dịch thất bại**, vừa có diagnostic mang mã dominance. `mustCompile` yêu cầu compiler chấp nhận. Nếu điều kiện không đúng, ném `AssertionError` để quá trình chạy test thất bại.

### Giới hạn và cách tăng độ bền cho bộ test thật

- **Mã diagnostic không phải hợp đồng API ổn định của Java Language Specification.** `getCode().contains("dominated")` phù hợp để minh họa với `javac` đã thử, nhưng nếu nâng JDK/compiler khác, cần kiểm chứng mã chẩn đoán mới. Bộ test production có thể định nghĩa một tập mã được chấp nhận theo phiên bản JDK mà CI hỗ trợ.
- **Một source có thể đồng thời có nhiều lỗi.** Harness minh họa tìm ít nhất một lỗi dominance. Nếu muốn chặt chẽ hơn, hãy kiểm tra tất cả diagnostics thuộc dạng kỳ vọng, giới hạn vị trí lỗi, hoặc bảo đảm source không chứa lỗi phụ bằng positive control và review fixture.
- **Positive control quan trọng.** Nó giúp phát hiện tình huống mọi lần compile đều thất bại vì cấu hình, classpath, release option hay lỗi source chung. Nếu không có đối chứng dương, một negative test đơn giản `!compiled` rất dễ cho kết quả dương tính giả.
- **Không dùng preview ngoài ý định.** Bài dùng `--release 21` và cú pháp Java 21 đã ổn định. Với các tính năng preview ở những JDK khác, phải cấu hình preview riêng và nêu rõ mục tiêu test; không trộn vào bộ test Java 21 ổn định.
- **Không thực thi bytecode từ fixture lỗi.** Negative test chỉ cần compiler từ chối; positive test kiểm tra compilation. Nếu còn muốn đối chiếu runtime, dùng bài test chuyên biệt trên bản source hợp lệ.

## 8. Chiến lược kiểm thử cho dự án và CI

Một module Java dùng nhiều pattern switch nên kết hợp các tầng:

| Tầng | Ví dụ | Kiểm chứng |
| --- | --- | --- |
| Compile-failure test | `CharSequence` trước `String` | Bị từ chối vì dominance |
| Compile-failure test | `case String s` trước `case String s when ...` | Bị từ chối vì dominance |
| Compile-failure test | Record pattern tổng quát trước nhánh cùng record có guard | Bị từ chối vì dominance |
| Compile-success test | Thứ tự hẹp → rộng | Biên dịch thành công |
| Compile-success test | Hai guard có điều kiện giao nhau không được compiler chứng minh | Biên dịch thành công, nhắc rằng không có lỗi không nghĩa là đúng nghiệp vụ |
| Runtime test | `"   "`, `"hello"`, số, `null` | Chọn đúng nhánh |
| Runtime test | Ngưỡng `length == 3, 4, 5, 6` | Nhánh guard đúng theo yêu cầu |
| Refactoring regression test | Đổi thứ tự hoặc thêm kiểu mới | Không vô tình che nhánh hoặc đổi hành vi |

Các bước áp dụng:

1. **Khóa phiên bản JDK trong CI**; sử dụng toolchain và tùy chọn `--release` nhất quán.
2. **Giữ những fixture source bị từ chối ở nơi riêng**; không đưa chúng vào `src/main/java` hoặc tập source được biên dịch tự động của module chính.
3. **Đặt tên test theo nguyên nhân lỗi**: `rejectBroadTypeBeforeSubtype`, `rejectUnguardedBeforeGuarded`, `rejectBroadRecordPatternBeforeGuarded`.
4. **Mỗi fixture chứa một nguyên nhân lỗi chủ đích** để chẩn đoán dễ đối chiếu.
5. **Cặp test âm/dương**: mã sai phải bị từ chối, mã sau sửa phải compile. Nếu một negative test bất ngờ thành công sau khi nâng JDK, hãy kiểm tra lại quy tắc theo JLS và hành vi compiler phiên bản đó trước khi sửa kỳ vọng.
6. **Kèm runtime tests** cho điều kiện Boolean không được compiler suy luận đầy đủ.

Không cần ép tất cả các test này vào cùng một lớp. Với dự án lớn, có thể dùng JUnit gọi Java Compiler API hoặc thư viện compile-testing phù hợp; harness độc lập ở phần 7 giúp thấy rõ cơ chế mà không phụ thuộc framework ngoài JDK.

## 9. Phân biệt dominance với exhaustiveness và những lỗi khác

### Dominance: nhánh sau bị nhánh trước che

~~~java
// CỐ Ý SAI.
case CharSequence cs -> "text";
case String s -> "string";
~~~

Compiler kiểm tra thứ tự/quan hệ bao phủ case pattern. **Sửa:** chuyển nhánh `String` lên trước.

### Exhaustiveness: còn giá trị chưa được xử lý

~~~java
// CỐ Ý SAI: Object có thể chứa nhiều kiểu khác.
String label = switch (input) {
    case String s -> "string";
    case null -> "null";
    // Không có nhánh cho Integer, Boolean, ...
};
~~~

Với `switch expression` trên `Object`, code thiếu nhánh bao phủ những kiểu khác; đây là lỗi **không exhaustive**, không phải dominance. **Sửa:** thêm `default` hoặc type pattern bao phủ phần còn lại, tùy thiết kế. Không nên nhầm loại lỗi khi ghi kết quả test.

### Type incompatibility: nhánh trả sai kiểu

~~~java
// CỐ Ý SAI trong ngữ cảnh đòi hỏi int.
int n = switch (input) {
    case String s -> "not an integer";
    case null -> 0;
    default -> 1;
};
~~~

Một nhánh trả `String` trong ngữ cảnh `int` dẫn đến lỗi kiểu. Nếu một negative test kỳ vọng dominance mà chỉ phát hiện lỗi này, test đã đánh trượt mục tiêu.

### Pattern variable scope

~~~java
// CỐ Ý SAI: text có thể chưa được ràng buộc.
if (input instanceof String text) {
    System.out.println(text);
}
System.out.println(text);
~~~

Lỗi phạm vi biến là một quy tắc khác của pattern matching; cũng nên kiểm thử riêng nếu module quan tâm nhưng không gộp với dominance fixture.

**Cách đặt tên kết quả:** `REJECTED_FOR_DOMINANCE`, `REJECTED_NOT_EXHAUSTIVE`, `REJECTED_FOR_TYPE_ERROR` rõ hơn một Boolean chung chung `shouldNotCompile`.

## 10. Checklist chất lượng cho compile-failure tests

Trước khi đưa test vào CI, hãy kiểm tra:

- Fixture có cú pháp Java **hợp lệ ngoài lỗi dominance** mà mình cố ý đưa vào không?
- Đã chỉ rõ JDK, `--release` và có cần preview hay không?
- Có cặp **positive control** để phát hiện lỗi môi trường và lỗi nguồn chung không?
- Assertion có phân biệt **lỗi dominance** với “bất kỳ lỗi biên dịch nào” không?
- Mỗi test có phạm vi nhỏ, tên rõ ràng và độc lập với test khác không?
- Những record patterns có component đúng số lượng/kiểu và null semantics như mong đợi không?
- Chẩn đoán được lấy từ compiler và có lưu ý về thay đổi mã diagnostic giữa JDK không?
- Có test runtime cho các guard mà compiler không thể suy luận quan hệ logic không?
- Có tránh cho fixture cố ý sai lọt vào build production không?
- Sau khi thay đổi thứ tự case hoặc thêm subtype, đã biên dịch và chạy lại cả test âm, test dương và test hành vi chưa?

## 11. Bài tập tự luyện có đáp án

### Bài 1 — Nhận biết dominance theo kiểu

Với `Object input`, đoạn sau có hợp lệ không?

~~~java
String result = switch (input) {
    case Number n -> "number";
    case Integer i -> "integer";
    case null -> "null";
    default -> "other";
};
~~~

**Đáp án:** Không. `Integer` là subtype của `Number` nên `case Number n` bao phủ hết những giá trị `Integer` mà case sau muốn nhận. Đảo thứ tự `Integer` lên trước `Number`.

### Bài 2 — Giữ guard cụ thể trước

Cho đoạn:

~~~java
// CỐ Ý SAI.
String category = switch (input) {
    case String s -> "string";
    case String s when s.length() == 0 -> "empty";
    case null -> "null";
    default -> "other";
};
~~~

**Đáp án:** `case String s when s.length() == 0` bị dominated bởi `case String s` trước. Sửa bằng cách đặt case có guard trước case String không guard. Cũng có thể dùng `s.isEmpty()` thay `s.length() == 0` nếu phù hợp yêu cầu.

### Bài 3 — Record pattern

Cho `record Box(int size) {}` và selector `Object input`:

~~~java
String result = switch (input) {
    case Box(var size) -> "box";
    case Box(var size) when size > 10 -> "big";
    case null -> "null";
    default -> "other";
};
~~~

**Đáp án:** Nhánh `Box(var size)` đầu bao phủ tất cả `Box` không null, vì vậy nhánh guard phía sau bị dominated. Đặt `case Box(var size) when size > 10` lên trước.

### Bài 4 — Compiler có phát hiện điều kiện giao nhau không?

Cho:

~~~java
String result = switch (input) {
    case Integer n when n > 10 -> "above 10";
    case Integer n when n > 20 -> "above 20";
    case Integer n -> "other integer";
    case null -> "null";
    default -> "other";
};
~~~

**Đáp án:** Không nên mong compiler chứng minh mọi quan hệ số học giữa hai guard để báo dominance. Mẫu tương tự có thể biên dịch, nhưng số `25` bị nhánh `n > 10` nhận trước nên không đi vào nhánh `n > 20`. Cần đặt `n > 20` trước `n > 10` và kiểm thử runtime ở các giá trị biên như `10`, `11`, `20`, `21`.

### Bài 5 — Negative test nào không đáng tin?

Một test chỉ viết:

~~~java
boolean success = compiler.getTask(/* ... */).call();
if (success) {
    throw new AssertionError("Should fail");
}
~~~

**Đáp án:** Test này có thể “PASS” vì bất kỳ lỗi nào: thiếu import, sai tên lớp công khai/tên file, loại `switch` không exhaustive, hoặc một lỗi cú pháp hoàn toàn không liên quan. Hãy thêm xác nhận chẩn đoán dominance và positive control, đồng thời giữ fixture càng nhỏ càng tốt.

## 12. Ghi nhớ và tài liệu chuẩn

- **Dominance** là quan hệ bao phủ giữa case pattern theo những quy tắc Java quy định; nhánh bị che có thể trở thành **lỗi biên dịch**.
- **Compile-failure test** cố ý cung cấp source sai và kỳ vọng compiler từ chối **đúng lý do**, không phải chỉ từ chối.
- Ba negative cases hữu ích: **kiểu cha trước kiểu con**, **pattern không guard trước guard chuyên biệt**, **record pattern tổng quát trước guarded record pattern**.
- Kèm **positive control** để phân biệt lỗi dominance với lỗi cấu hình/cú pháp; không đưa fixture cố ý sai vào build nguồn chính.
- **Compiler không giải mọi quan hệ giữa guard tùy ý**. Điều kiện giao nhau và ưu tiên nghiệp vụ vẫn cần kiểm thử runtime.
- Với `javax.tools.JavaCompiler`, có thể tự động biên dịch source từ chuỗi và kiểm tra chẩn đoán, không cần tạo tệp tạm cho mỗi negative test.
- Duy trì bộ kiểm thử theo phiên bản compiler và không phụ thuộc tuyệt đối vào câu chữ/mã diagnostic không được đặc tả ổn định.

**Tài liệu tham khảo:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441); [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [Java Language Specification SE 21 — `switch` labels, pattern dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1); [Java 21 — JavaCompiler API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html); [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
