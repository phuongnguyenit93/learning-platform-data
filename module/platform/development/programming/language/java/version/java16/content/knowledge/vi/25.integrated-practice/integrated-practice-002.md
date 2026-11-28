# Tạo báo cáo nhóm theo khóa record bằng Stream và method reference

Một báo cáo tổng hợp thường cần gom các bản ghi theo nhiều thuộc tính, tính số lượng và điểm trung bình, rồi sắp xếp kết quả để hiển thị. Java 16 có thể giải quyết bài toán này bằng **record**, **Stream API**, **Collectors.groupingBy**, **Collectors.teeing** và **method reference**.

Trong bài thực hành, ta xây dựng báo cáo điểm học viên theo hai khóa: phòng ban và cấp độ. Một record `GroupKey` đại diện cho khóa nhóm; `groupingBy` gom học viên theo khóa đó; các collector downstream tính thống kê và thu thập tên; cuối cùng Stream chuyển map thành danh sách báo cáo có thứ tự.

Các kỹ thuật này vẫn áp dụng trong Java hiện đại. Record được hoàn thiện trong Java 16, `Stream.toList()` có từ Java 16, còn `Collectors.teeing()` đã có từ Java 12. Bài dùng cú pháp Java 16 và không dựa vào API thử nghiệm hoặc đã lỗi thời.

## 1. Mục tiêu và dữ liệu đầu vào

Giả sử một ứng dụng đào tạo có danh sách học viên. Mỗi học viên có mã, tên, phòng ban, cấp độ và điểm số. Báo cáo cần hiển thị:

- Phòng ban và cấp độ.
- Số học viên trong từng nhóm.
- Điểm trung bình.
- Điểm cao nhất.
- Danh sách tên học viên.

Dữ liệu mẫu:

| Mã | Học viên | Phòng ban | Cấp độ | Điểm |
|---|---|---|---|---:|
| S01 | An | Engineering | Junior | 86 |
| S02 | Bình | Engineering | Junior | 91 |
| S03 | Chi | Engineering | Senior | 95 |
| S04 | Hà | Engineering | Senior | 89 |
| S05 | Dũng | Sales | Junior | 78 |
| S06 | Giang | Sales | Junior | 82 |

Ta muốn kết quả có ba nhóm:

- Engineering / Junior: 2 học viên, trung bình 88.5, cao nhất 91.
- Engineering / Senior: 2 học viên, trung bình 92.0, cao nhất 95.
- Sales / Junior: 2 học viên, trung bình 80.0, cao nhất 82.

Nếu nhóm theo riêng phòng ban, Junior và Senior sẽ bị gộp chung. Vì vậy, khóa nhóm cần chứa cả `department` và `level`.

## 2. Dùng record làm khóa nhóm

Record phù hợp với các kiểu dữ liệu chủ yếu dùng để mang giá trị. Java tự sinh constructor, accessor, `equals()`, `hashCode()` và `toString()` dựa trên các component của record.

Khai báo khóa nhóm:

```java
record GroupKey(String department, String level) {}
```

Hai đối tượng `GroupKey` có cùng `department` và `level` sẽ bằng nhau theo giá trị:

```java
var first = new GroupKey("Engineering", "Junior");
var second = new GroupKey("Engineering", "Junior");

System.out.println(first.equals(second)); // true
```

Đặc điểm này làm record trở thành khóa tự nhiên cho `Map`. `Collectors.groupingBy()` dùng kết quả của hàm phân loại làm key; các học viên có cùng khóa record sẽ được đưa vào cùng một nhóm.

Khóa nhóm nên bất biến. `String` là kiểu bất biến, do đó record trên không giữ một đối tượng mutable có thể làm thay đổi kết quả `equals()` hoặc `hashCode()` sau khi đã được đưa vào map.

Nếu component của record là collection hoặc một object mutable, cần cân nhắc sao chép phòng vệ và bảo đảm dữ liệu dùng làm khóa không thay đổi trong thời gian nằm trong map.

## 3. Khai báo record cho học viên và kết quả

Ta dùng một record cho dữ liệu đầu vào:

```java
record Student(
        String id,
        String name,
        String department,
        String level,
        int score
) {
    GroupKey groupKey() {
        return new GroupKey(department, level);
    }
}
```

Phương thức `groupKey()` tạo khóa nhóm từ hai component. Khi truyền `Student::groupKey` vào `groupingBy`, Stream sẽ gọi phương thức này cho từng học viên.

Record chứa thống kê của một nhóm:

```java
record GroupMetrics(
        long count,
        double average,
        int highestScore,
        List<String> names
) {
    GroupMetrics {
        names = List.copyOf(names);
    }
}
```

`List.copyOf()` tạo bản sao không thể sửa đổi thông qua danh sách được trả về. Điều này giúp `GroupMetrics` không để lộ danh sách mutable do collector tạo ra.

Record báo cáo gắn khóa nhóm với thống kê:

```java
record GroupReport(GroupKey key, GroupMetrics metrics) {}
```

Việc tách `GroupKey`, `GroupMetrics` và `GroupReport` làm rõ ba trách nhiệm: nhận diện nhóm, tính số liệu và biểu diễn kết quả. Trong một ứng dụng lớn, các record này có thể được đặt thành kiểu top-level trong những file riêng.

## 4. Gom nhóm bằng Collectors.groupingBy

`groupingBy()` nhận một classifier function. Function này nhận phần tử đầu vào và trả về khóa nhóm.

Ví dụ đơn giản:

```java
Map<GroupKey, List<Student>> groups =
        students.stream()
                .collect(Collectors.groupingBy(Student::groupKey));
```

Với mỗi `Student`, method reference `Student::groupKey` tương đương lambda:

```java
student -> student.groupKey()
```

Kết quả là một `Map<GroupKey, List<Student>>`. Mỗi key là một giá trị `GroupKey`, còn value là danh sách học viên thuộc nhóm đó.

Cách này dễ hiểu, nhưng nếu chỉ cần thống kê, giữ toàn bộ danh sách trung gian có thể không cần thiết. Ta có thể truyền một downstream collector để tổng hợp từng nhóm ngay trong quá trình collect.

## 5. Kết hợp nhiều phép tổng hợp bằng Collectors.teeing

`Collectors.teeing()` kết hợp hai downstream collector trên cùng một luồng phần tử. Sau khi cả hai collector hoàn tất, một merger function nhận hai kết quả và tạo kết quả cuối cùng.

Ta cần hai nhánh:

1. `summarizingInt(Student::score)` tính số lượng, tổng, trung bình, nhỏ nhất và lớn nhất của điểm.
2. `mapping(Student::name, toList())` lấy tên học viên và thu thập thành danh sách.

Kết hợp chúng:

```java
var metricsCollector = Collectors.teeing(
        Collectors.summarizingInt(Student::score),
        Collectors.mapping(Student::name, Collectors.toList()),
        (statistics, names) -> new GroupMetrics(
                statistics.getCount(),
                statistics.getAverage(),
                statistics.getMax(),
                names
        )
);
```

`teeing()` nhận ba đối số:

- Collector thứ nhất: tính `IntSummaryStatistics`.
- Collector thứ hai: thu thập danh sách tên.
- Merger: kết hợp hai kết quả thành `GroupMetrics`.

Các method reference `Student::score` và `Student::name` trỏ tới accessor được record tự sinh. Chúng ngắn gọn khi một phương thức hiện có khớp với functional interface mà collector yêu cầu.

Merger vẫn dùng lambda vì cần kết hợp hai kết quả độc lập (`statistics` và `names`) thành một object mới.

## 6. Hoàn thiện phép collect theo khóa record

Ta truyền downstream collector vừa tạo vào overload của `groupingBy`:

```java
Map<GroupKey, GroupMetrics> metricsByGroup =
        students.stream()
                .collect(Collectors.groupingBy(
                        Student::groupKey,
                        metricsCollector
                ));
```

Toàn bộ phép tổng hợp có thể viết trực tiếp:

```java
Map<GroupKey, GroupMetrics> metricsByGroup =
        students.stream()
                .collect(Collectors.groupingBy(
                        Student::groupKey,
                        Collectors.teeing(
                                Collectors.summarizingInt(Student::score),
                                Collectors.mapping(
                                        Student::name,
                                        Collectors.toList()
                                ),
                                (statistics, names) -> new GroupMetrics(
                                        statistics.getCount(),
                                        statistics.getAverage(),
                                        statistics.getMax(),
                                        names
                                )
                        )
                ));
```

Kết quả có dạng khái niệm:

```text
Engineering / Junior
  count = 2
  average = 88.5
  highest = 91
  names = [An, Bình]

Engineering / Senior
  count = 2
  average = 92.0
  highest = 95
  names = [Chi, Hà]

Sales / Junior
  count = 2
  average = 80.0
  highest = 82
  names = [Dũng, Giang]
```

Lưu ý: downstream collector chỉ nhận các phần tử của một nhóm, không nhận trực tiếp key mà `groupingBy` đang dùng. Vì thế, map kết quả có key `GroupKey` và value `GroupMetrics`; bước sau sẽ ghép chúng thành `GroupReport`.

## 7. Chuyển Map thành danh sách báo cáo

`groupingBy()` mặc định tạo map mà thứ tự duyệt không được bảo đảm. Nếu báo cáo cần thứ tự ổn định, hãy sắp xếp rõ ràng trước khi xuất.

```java
List<GroupReport> reports =
        metricsByGroup.entrySet()
                .stream()
                .map(entry -> new GroupReport(
                        entry.getKey(),
                        entry.getValue()
                ))
                .sorted(Comparator.comparing(
                        GroupReport::key,
                        Comparator.comparing(GroupKey::department)
                                .thenComparing(GroupKey::level)
                ))
                .toList();
```

Giải thích các bước:

- `entrySet().stream()` tạo stream từ các cặp key/value.
- `map()` chuyển mỗi entry thành `GroupReport`.
- `GroupReport::key` lấy khóa nhóm từ báo cáo.
- `GroupKey::department` và `GroupKey::level` tạo thứ tự sắp xếp theo phòng ban rồi cấp độ.
- `toList()` thu kết quả thành danh sách.

`Stream.toList()` được bổ sung trong Java 16 và trả về danh sách không thể sửa đổi. Nếu bước tiếp theo cần thêm hoặc xóa phần tử, có thể dùng:

```java
List<GroupReport> mutableReports =
        reports.stream()
                .collect(Collectors.toCollection(ArrayList::new));
```

Không nên dựa vào thứ tự hiện tại của `HashMap` để trình bày báo cáo. Sắp xếp tường minh làm kết quả dễ kiểm tra và ổn định giữa các lần chạy.

## 8. Dùng method reference để định dạng và xuất báo cáo

Ta viết một phương thức nhận `GroupReport` và trả về một dòng văn bản:

```java
static String format(GroupReport report) {
    GroupKey key = report.key();
    GroupMetrics metrics = report.metrics();

    return String.format(
            Locale.ROOT,
            "%-14s | %-10s | %5d | %8.1f | %4d | %s",
            key.department(),
            key.level(),
            metrics.count(),
            metrics.average(),
            metrics.highestScore(),
            String.join(", ", metrics.names())
    );
}
```

Sau đó dùng method reference cho phép biến đổi và xuất:

```java
reports.stream()
        .map(GroupedReport::format)
        .forEach(System.out::println);
```

Hai method reference có vai trò khác nhau:

- `GroupedReport::format` là tham chiếu tới phương thức static nhận một `GroupReport`.
- `System.out::println` là tham chiếu tới phương thức instance `println` trên đối tượng `System.out`.

Chúng tương ứng với:

```java
reports.stream()
        .map(report -> GroupedReport.format(report))
        .forEach(line -> System.out.println(line));
```

Method reference không phải lúc nào cũng làm code dễ đọc hơn. Dùng nó khi phương thức đã có thể diễn đạt trực tiếp thao tác cần thực hiện; nếu cần biến đổi nhiều bước hoặc logic có điều kiện, lambda thường rõ ràng hơn.

## 9. Chương trình hoàn chỉnh chạy trên Java 16

Tạo file `GroupedReport.java`:

```java
package vn.example.report;

import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Comparator;
import java.util.stream.Collectors;

public class GroupedReport {

    public static void main(String[] args) {
        List<Student> students = List.of(
                new Student("S01", "An", "Engineering", "Junior", 86),
                new Student("S02", "Bình", "Engineering", "Junior", 91),
                new Student("S03", "Chi", "Engineering", "Senior", 95),
                new Student("S04", "Hà", "Engineering", "Senior", 89),
                new Student("S05", "Dũng", "Sales", "Junior", 78),
                new Student("S06", "Giang", "Sales", "Junior", 82)
        );

        List<GroupReport> reports = buildReport(students);

        System.out.println(
                "Department     | Level      | Count | Average | High | Students"
        );
        System.out.println(
                "-------------------------------------------------------------------"
        );

        reports.stream()
                .map(GroupedReport::format)
                .forEach(System.out::println);
    }

    static List<GroupReport> buildReport(List<Student> students) {
        Objects.requireNonNull(students, "students");

        Map<GroupKey, GroupMetrics> metricsByGroup =
                students.stream()
                        .collect(Collectors.groupingBy(
                                Student::groupKey,
                                Collectors.teeing(
                                        Collectors.summarizingInt(Student::score),
                                        Collectors.mapping(
                                                Student::name,
                                                Collectors.toList()
                                        ),
                                        (statistics, names) -> new GroupMetrics(
                                                statistics.getCount(),
                                                statistics.getAverage(),
                                                statistics.getMax(),
                                                names
                                        )
                                )
                        ));

        return metricsByGroup.entrySet()
                .stream()
                .map(entry -> new GroupReport(
                        entry.getKey(),
                        entry.getValue()
                ))
                .sorted(Comparator.comparing(
                        GroupReport::key,
                        Comparator.comparing(GroupKey::department)
                                .thenComparing(GroupKey::level)
                ))
                .toList();
    }

    static String format(GroupReport report) {
        GroupKey key = report.key();
        GroupMetrics metrics = report.metrics();

        return String.format(
                Locale.ROOT,
                "%-14s | %-10s | %5d | %8.1f | %4d | %s",
                key.department(),
                key.level(),
                metrics.count(),
                metrics.average(),
                metrics.highestScore(),
                String.join(", ", metrics.names())
        );
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field);
        String normalized = value.trim();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }

        return normalized;
    }

    private record Student(
            String id,
            String name,
            String department,
            String level,
            int score
    ) {
        Student {
            id = requireText(id, "id");
            name = requireText(name, "name");
            department = requireText(department, "department");
            level = requireText(level, "level");

            if (score < 0 || score > 100) {
                throw new IllegalArgumentException(
                        "score must be between 0 and 100"
                );
            }
        }

        GroupKey groupKey() {
            return new GroupKey(department, level);
        }
    }

    private record GroupKey(String department, String level) {
        GroupKey {
            department = requireText(department, "department");
            level = requireText(level, "level");
        }
    }

    private record GroupMetrics(
            long count,
            double average,
            int highestScore,
            List<String> names
    ) {
        GroupMetrics {
            names = List.copyOf(names);
        }
    }

    private record GroupReport(
            GroupKey key,
            GroupMetrics metrics
    ) {
        GroupReport {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(metrics, "metrics");
        }
    }
}
```

Trong ví dụ này:

- Record mô hình hóa dữ liệu đầu vào, khóa nhóm và kết quả.
- `groupingBy()` tạo nhóm theo nhiều component của record key.
- `teeing()` kết hợp thống kê điểm và danh sách tên trong một lần collect.
- Method reference biểu đạt các accessor và thao tác định dạng.
- `toList()` tạo danh sách kết quả không thể sửa đổi.
- Constructor compact của record kiểm tra dữ liệu và sao chép danh sách kết quả.

## 10. Biên dịch và chạy

Cấu trúc thư mục:

```text
project/
  src/
    vn/
      example/
        report/
          GroupedReport.java
  out/
```

Kiểm tra JDK:

```bash
java -version
javac -version
```

Biên dịch với Java 16 language/API target:

```bash
javac --release 16 -d out src/vn/example/report/GroupedReport.java
```

Chạy chương trình:

```bash
java -cp out vn.example.report.GroupedReport
```

Kết quả dự kiến:

```text
Department     | Level      | Count | Average | High | Students
-------------------------------------------------------------------
Engineering    | Junior     |     2 |     88.5 |   91 | An, Bình
Engineering    | Senior     |     2 |     92.0 |   95 | Chi, Hà
Sales          | Junior     |     2 |     80.0 |   82 | Dũng, Giang
```

Nếu dùng JDK mới hơn để biên dịch, `--release 16` giúp kiểm tra rằng mã chỉ sử dụng API có trong Java 16. Khi triển khai trên JDK mới, có thể biên dịch theo release target mà dự án hỗ trợ.

## 11. Vì sao record key phù hợp với groupingBy?

Một khóa nhóm nên có equality và hash code ổn định. Record tự sinh `equals()` và `hashCode()` dựa trên các component, do đó hai khóa có cùng giá trị sẽ được xem là cùng nhóm.

Ví dụ:

```java
var a = new GroupKey("Engineering", "Junior");
var b = new GroupKey("Engineering", "Junior");

Map<GroupKey, Integer> counts = new java.util.HashMap<>();
counts.put(a, 2);
counts.merge(b, 1, Integer::sum);

System.out.println(counts.get(a)); // 3
```

Nếu dùng một class thông thường mà quên override `equals()` và `hashCode()`, các instance khác nhau có thể không được xem là cùng khóa dù thuộc tính giống nhau. Record tránh được lỗi thường gặp này khi mô hình hóa khóa theo giá trị.

Tuy nhiên, record chỉ tạo equality theo component. Nếu component chứa object mutable, thay đổi object đó có thể ảnh hưởng tính ổn định của khóa. Với key trong map, nên dùng component bất biến như `String`, enum hoặc các record bất biến khác.

## 12. Chọn collector phù hợp với yêu cầu báo cáo

Không phải báo cáo nào cũng cần `teeing()`. Chọn collector theo dữ liệu thực sự cần.

| Nhu cầu | Collector phù hợp |
|---|---|
| Gom phần tử thành danh sách theo nhóm | `groupingBy(classifier)` |
| Đếm phần tử theo nhóm | `counting()` |
| Tính trung bình số nguyên | `averagingInt()` |
| Tính tổng và thống kê min/max/average/count | `summarizingInt()` |
| Chuyển đổi phần tử trước khi collect | `mapping()` |
| Kết hợp hai kết quả downstream | `teeing()` |
| Tạo map có thứ tự theo key | `groupingBy(classifier, mapFactory, downstream)` |

Nếu chỉ cần số học viên và điểm trung bình, có thể dùng collector đơn giản hơn:

```java
Map<GroupKey, Double> averageByGroup =
        students.stream()
                .collect(Collectors.groupingBy(
                        Student::groupKey,
                        Collectors.averagingInt(Student::score)
                ));
```

Nếu cần cả thống kê lẫn danh sách tên, `teeing()` giúp kết hợp hai downstream collector mà không phải duyệt lại danh sách học viên của từng nhóm trong code ứng dụng.

## 13. Xử lý dữ liệu thiếu, nhóm rỗng và thứ tự

`groupingBy()` chỉ tạo key cho những nhóm có phần tử trong stream. Nếu báo cáo cần hiển thị cả nhóm chưa có học viên với count bằng 0, phải có danh sách nhóm kỳ vọng và bổ sung các nhóm còn thiếu sau bước collect.

Ví dụ:

```java
List<GroupKey> expectedGroups = List.of(
        new GroupKey("Engineering", "Junior"),
        new GroupKey("Engineering", "Senior"),
        new GroupKey("Sales", "Junior"),
        new GroupKey("Support", "Intern")
);
```

Sau đó có thể tạo báo cáo đầy đủ từ `expectedGroups`, tra cứu metrics đã collect và cung cấp metrics mặc định cho nhóm chưa xuất hiện.

Với dữ liệu đầu vào không hợp lệ, cần thống nhất chính sách:

- Từ chối record thiếu key như phòng ban hoặc cấp độ.
- Xác định điểm null/không có có được bỏ qua hay phải báo lỗi.
- Không coi điểm 0 là dữ liệu thiếu nếu 0 là giá trị hợp lệ.
- Chuẩn hóa chữ hoa/thường và khoảng trắng trước khi tạo khóa nếu quy tắc nghiệp vụ yêu cầu.

Record trong bài kiểm tra các trường bắt buộc và giới hạn điểm từ 0 đến 100. Quy tắc thực tế cần điều chỉnh theo miền nghiệp vụ.

## 14. Dùng parallel stream có phù hợp không?

Có thể thay `students.stream()` bằng `students.parallelStream()`, nhưng không nên mặc định rằng parallel sẽ nhanh hơn.

`groupingBy()` trong parallel stream có thể tạo các map trung gian rồi kết hợp chúng. Chi phí merge, kích thước nhóm, số core và số phần tử ảnh hưởng đến hiệu quả. Nếu dữ liệu nhỏ, xử lý tuần tự thường đơn giản và có thể nhanh hơn.

Cân nhắc parallel stream khi:

- Tập dữ liệu đủ lớn.
- Phép tính trong mỗi phần tử có chi phí đáng kể.
- Collector có thể kết hợp kết quả an toàn.
- Đã benchmark với tải và môi trường gần production.

`groupingByConcurrent()` là lựa chọn khác khi cần concurrent reduction và không yêu cầu thứ tự kết quả. Tuy nhiên, nó không tự động nhanh hơn trong mọi trường hợp. Hãy cân nhắc tính chất nguồn stream, mức độ tranh chấp giữa các key và yêu cầu ordering.

Không sửa một collection dùng chung từ bên trong `map()` hoặc `forEach()` của parallel stream. Hãy để collector quản lý việc tích lũy kết quả.

## 15. Những lỗi thường gặp

**Dùng nhiều field rời rạc làm key.** Nếu nhóm theo cả phòng ban và cấp độ, tạo `GroupKey` giúp equality/hash code dựa trên giá trị được xử lý nhất quán.

**Dùng record chứa component mutable làm key.** Thay đổi component sau khi đưa key vào map có thể làm lookup không còn hoạt động như mong đợi. Ưu tiên component bất biến.

**Cho rằng downstream collector nhận được key nhóm.** Collector trong `groupingBy(classifier, downstream)` chỉ nhận các phần tử của nhóm. Muốn ghép key vào báo cáo, hãy chuyển `entrySet()` sau khi collect.

**Giả định map luôn có thứ tự.** Map mặc định không bảo đảm thứ tự hiển thị. Sắp xếp entries hoặc report trước khi xuất.

**Duyệt danh sách nhiều lần để tính từng chỉ số.** Khi cần nhiều kết quả, `summarizingInt()` và `teeing()` có thể gom các phép tổng hợp vào cùng một collector.

**Nhầm `Stream.toList()` với danh sách mutable.** `toList()` trả về danh sách không thể sửa đổi. Nếu cần danh sách mutable, chọn collector tạo collection cụ thể.

**Dùng method reference cho mọi lambda.** Nếu cần xử lý nhiều bước hoặc điều kiện, lambda có thể dễ đọc hơn.

**Cho rằng `parallelStream()` luôn tăng tốc.** Chi phí chia và kết hợp dữ liệu có thể lớn hơn lợi ích song song, nhất là với tập dữ liệu nhỏ.

**Không kiểm tra dữ liệu trước khi grouping.** Key null, chuỗi rỗng hoặc dữ liệu không chuẩn hóa có thể tạo nhóm sai hoặc làm phép collect thất bại. Kiểm tra đầu vào theo quy tắc nghiệp vụ.

## 16. Ghi nhớ

- Record phù hợp để biểu diễn khóa nhóm theo giá trị.
- `equals()` và `hashCode()` được sinh dựa trên component của record.
- `Student::groupKey` là classifier method reference cho `groupingBy()`.
- `Collectors.groupingBy()` gom các phần tử theo khóa.
- `Collectors.teeing()` kết hợp hai downstream collector thành một kết quả.
- `summarizingInt()` cung cấp count, sum, average, min và max.
- `mapping()` chuyển phần tử trước khi collector downstream nhận dữ liệu.
- `Map.entrySet().stream()` giúp chuyển map thành báo cáo có thể sắp xếp.
- `Comparator.comparing()` và method reference giúp mô tả thứ tự theo nhiều component.
- `Stream.toList()` có từ Java 16 và trả về danh sách không thể sửa đổi.
- Parallel stream cần benchmark; không phải lựa chọn mặc định cho mọi báo cáo.
- `Collectors.teeing()` có từ Java 12, vẫn dùng được trong Java 16 và các JDK hiện đại.

Bài thực hành kết hợp record, Stream và method reference để tạo báo cáo nhóm theo nhiều thuộc tính. Record cung cấp khóa giá trị ổn định; collector đảm nhiệm việc phân nhóm và tổng hợp; method reference làm rõ các phép truy cập và chuyển đổi. Cấu trúc này có thể mở rộng sang báo cáo doanh thu theo khu vực, số đơn hàng theo trạng thái hoặc thống kê nhân sự theo phòng ban và cấp bậc.

## Tài liệu tham khảo

- [JEP 395 – Records](https://openjdk.org/jeps/395) — record được hoàn thiện trong Java 16.
- [Java Language Specification, Java SE 16 – Records](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html#jls-8.10) — khai báo record và ngữ nghĩa của record class.
- [Stream API – Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html) — Stream operations và `Stream.toList()`.
- [Collectors – Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Collectors.html) — `groupingBy`, `teeing`, `mapping` và các collector thống kê.
- [Method References – The Java Tutorials](https://docs.oracle.com/javase/tutorial/java/javaOO/methodreferences.html) — cú pháp và các dạng method reference.

