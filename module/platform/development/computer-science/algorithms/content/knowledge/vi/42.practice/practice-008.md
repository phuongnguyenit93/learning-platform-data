# Tìm kiếm văn bản với một mẫu, nhiều mẫu và nhiều truy vấn

> **Chủ đề:** Computer Science Algorithms → **Thực hành tổng hợp**. Chọn thuật toán theo workload: **KMP** cho một pattern, **Aho–Corasick** cho dictionary pattern đã biết, **Suffix Array** cho nhiều query trên một text tĩnh. Bài quy định overlap, duplicate ID, pattern rỗng và Unicode; gồm bốn chương trình Java 17, lệnh chạy, stdout và bộ kiểm thử differential có seed cố định.

## 1. Hợp đồng và chỉ số

Cho text T dài n và pattern P dài m, tìm mọi start i sao cho `T[i..i+m)=P`. Vị trí là 0-based start index, đoạn match nửa mở.

```text
T = a b a b a
    0 1 2 3 4
P = a b a
```

Kết quả `[0,2]`; hai match chồng lấp tại index2. Không được nhảy qua toàn bộ pattern sau match đầu nếu cần mọi occurrence.

Quy ước của bài:

- Exact match, phân biệt hoa/thường.
- Offset là 0-based UTF-16 code unit của Java `String`.
- Trả mọi occurrence, kể cả overlap.
- Pattern null/rỗng bị từ chối bằng `IllegalArgumentException`.
- Text rỗng hợp lệ; pattern không rỗng cho kết quả rỗng.
- Aho giữ pattern ID riêng kể cả pattern trùng nội dung.

Pattern rỗng có thể được định nghĩa là match tại n+1 ranh giới, nhưng bài này từ chối nó để các API thống nhất. `String.charAt()` đếm UTF-16 code unit, không phải code point/grapheme. Nếu cần index code point, chuyển qua `codePoints().toArray()` và chạy trên `int[]`. Nếu cần normalization/case-folding, áp dụng cùng chính sách cho text và pattern trước khi tìm.

## 2. Naive search làm oracle

Thử mọi start i từ0 đến n−m rồi so từng ký tự. Worst-case O(nm) thời gian, O(1) bộ nhớ phụ ngoài output. Cách này đơn giản, độc lập và phù hợp làm oracle cho input ngắn. Ví dụ `T="aaaaaaaaab"`, `P="aaaaab"` làm naive lặp lại nhiều phép so sánh prefix dài.

## 3. KMP: một pattern

KMP tiền xử lý pattern thành prefix function `pi`. `pi[i]` là độ dài border dài nhất của `P[0..i]`: vừa là prefix vừa là suffix, không tính toàn bộ đoạn.

```text
P  = a b a b a c
pi = 0 0 1 2 3 0
```

Khi j ký tự đã khớp nhưng ký tự kế tiếp mismatch, chuyển `j=pi[j-1]` thay vì đưa j về0. Khi match đủ m ký tự, ghi `i-m+1`, rồi tiếp tục với `j=pi[j-1]` để giữ overlap.

Prefix preprocessing O(m), scan O(n), tổng **O(n+m)** thời gian và O(m) bộ nhớ prefix ngoài output O(z). Nếu pattern dùng cho nhiều text, build pi một lần rồi reuse. Với stream nhiều chunk, giữ j qua ranh giới chunk.

### 3.1. Java 17 — KmpSinglePatternDemo

Lưu file **KmpSinglePatternDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class KmpSinglePatternDemo {
    static int[] prefix(String p) {
        int[] pi = new int[p.length()];
        int j = 0;
        for (int i = 1; i < p.length(); i++) {
            while (j > 0 && p.charAt(i) != p.charAt(j))
                j = pi[j - 1];
            if (p.charAt(i) == p.charAt(j)) j++;
            pi[i] = j;
        }
        return pi;
    }

    static List<Integer> findAll(String text, String p) {
        if (text == null || p == null || p.isEmpty())
            throw new IllegalArgumentException("Invalid input");
        int[] pi = prefix(p);
        List<Integer> out = new ArrayList<>();
        int j = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            while (j > 0 && c != p.charAt(j)) j = pi[j - 1];
            if (c == p.charAt(j)) j++;
            if (j == p.length()) {
                out.add(i - p.length() + 1);
                j = pi[j - 1];
            }
        }
        return out;
    }

    static List<Integer> naive(String text, String p) {
        if (text == null || p == null || p.isEmpty())
            throw new IllegalArgumentException("Invalid input");
        List<Integer> out = new ArrayList<>();
        for (int i = 0; i + p.length() <= text.length(); i++)
            if (text.startsWith(p, i)) out.add(i);
        return out;
    }

    public static void main(String[] args) {
        System.out.println("matches=" + findAll("ababa", "aba"));
        System.out.println("overlaps=" + findAll("aaaa", "aa"));
        System.out.println("naive oracle="
                + (findAll("ababa", "aba").equals(naive("ababa", "aba"))
                && findAll("aaaa", "aa").equals(naive("aaaa", "aa"))));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 KmpSinglePatternDemo.java
java KmpSinglePatternDemo
```

Stdout:

```text
matches=[0, 2]
overlaps=[0, 1, 2]
naive oracle=true
```

## 4. Aho–Corasick: nhiều pattern trong một text

Aho–Corasick ghép dictionary thành **trie**, thêm failure link và output link để quét text một lượt.

- Trie node biểu diễn prefix; terminal list lưu pattern ID.
- Failure link trỏ đến suffix dài nhất vẫn là prefix của pattern.
- Output link trỏ đến terminal suffix gần nhất, tránh copy output list ở mọi node.

Với patterns `"he"` và `"she"`, khi match `"she"` phải báo cả `"she"` lẫn suffix `"he"`.

Dùng BFS xây failure link. Với cạnh `v --c--> u`, đi từ `fail[v]` lên đến node có cạnh c hoặc root; đặt `fail[u]` bằng node đích nếu có, nếu không bằng root. Output link trỏ tới failure node nếu terminal, nếu không kế thừa output link của nó.

Khi scan, nếu state không có cạnh c thì đi failure link đến khi có cạnh hoặc root. Sau khi chuyển state, phát terminal hiện tại và các terminal theo output link. Overlap được tìm tự nhiên; duplicate pattern giữ ID riêng.

Gọi S là tổng độ dài patterns, n là text, z là số occurrence. Với HashMap lookup O(1) kỳ vọng, build O(S), scan O(n+z), bộ nhớ O(S). Chương trình sort output theo `(start,patternId)`, thêm O(z log z).

### 4.1. Java 17 — AhoCorasickMultiPatternDemo

Lưu file **AhoCorasickMultiPatternDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class AhoCorasickMultiPatternDemo {
    record Match(int start, int patternId) {}

    static final class Node {
        final Map<Character, Integer> next = new HashMap<>();
        final List<Integer> terminal = new ArrayList<>();
        int fail = 0, outputLink = -1;
    }

    static final class Automaton {
        final List<String> patterns;
        final List<Node> nodes = new ArrayList<>();

        Automaton(List<String> input) {
            if (input == null) throw new IllegalArgumentException("Null");
            for (String p : input)
                if (p == null || p.isEmpty())
                    throw new IllegalArgumentException("Empty pattern");
            patterns = List.copyOf(input);
            nodes.add(new Node());
            for (int id = 0; id < patterns.size(); id++) {
                int state = 0;
                String p = patterns.get(id);
                for (int i = 0; i < p.length(); i++) {
                    char c = p.charAt(i);
                    Integer next = nodes.get(state).next.get(c);
                    if (next == null) {
                        next = nodes.size();
                        nodes.get(state).next.put(c, next);
                        nodes.add(new Node());
                    }
                    state = next;
                }
                nodes.get(state).terminal.add(id);
            }
            buildFailureLinks();
        }

        private void buildFailureLinks() {
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            for (int child : nodes.get(0).next.values()) queue.add(child);
            while (!queue.isEmpty()) {
                int state = queue.remove();
                for (Map.Entry<Character, Integer> edge
                        : nodes.get(state).next.entrySet()) {
                    char c = edge.getKey();
                    int child = edge.getValue();
                    int f = nodes.get(state).fail;
                    while (f != 0 && !nodes.get(f).next.containsKey(c))
                        f = nodes.get(f).fail;
                    Integer target = nodes.get(f).next.get(c);
                    nodes.get(child).fail = target == null ? 0 : target;
                    int suffix = nodes.get(child).fail;
                    nodes.get(child).outputLink =
                            !nodes.get(suffix).terminal.isEmpty()
                            ? suffix : nodes.get(suffix).outputLink;
                    queue.add(child);
                }
            }
        }

        List<Match> findAll(String text) {
            if (text == null) throw new IllegalArgumentException("Null text");
            List<Match> out = new ArrayList<>();
            int state = 0;
            for (int i = 0; i < text.length(); i++) {
                char c = text.charAt(i);
                while (state != 0 && !nodes.get(state).next.containsKey(c))
                    state = nodes.get(state).fail;
                state = nodes.get(state).next.getOrDefault(c, 0);
                for (int v = state; v != -1; v = nodes.get(v).outputLink)
                    for (int id : nodes.get(v).terminal)
                        out.add(new Match(i - patterns.get(id).length() + 1, id));
            }
            out.sort(Comparator.comparingInt(Match::start)
                    .thenComparingInt(Match::patternId));
            return out;
        }
    }

    static List<Match> naive(String text, List<String> patterns) {
        if (text == null || patterns == null)
            throw new IllegalArgumentException("Null input");
        List<Match> out = new ArrayList<>();
        for (int id = 0; id < patterns.size(); id++) {
            String p = patterns.get(id);
            if (p == null || p.isEmpty())
                throw new IllegalArgumentException("Empty pattern");
            for (int i = 0; i + p.length() <= text.length(); i++)
                if (text.startsWith(p, i)) out.add(new Match(i, id));
        }
        out.sort(Comparator.comparingInt(Match::start)
                .thenComparingInt(Match::patternId));
        return out;
    }

    static String format(List<Match> matches, List<String> patterns) {
        List<String> labels = new ArrayList<>();
        for (Match m : matches)
            labels.add(m.start() + ":" + patterns.get(m.patternId())
                    + "#" + m.patternId());
        return labels.toString();
    }

    public static void main(String[] args) {
        List<String> p = List.of("he", "she", "hers", "his", "he");
        List<Match> found = new Automaton(p).findAll("ushers");
        System.out.println("matches=" + format(found, p));
        List<String> overlap = List.of("a", "aa", "aaa");
        List<Match> many = new Automaton(overlap).findAll("aaaa");
        System.out.println("overlapCount=" + many.size());
        System.out.println("naive oracle="
                + (found.equals(naive("ushers", p))
                && many.equals(naive("aaaa", overlap))));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 AhoCorasickMultiPatternDemo.java
java AhoCorasickMultiPatternDemo
```

Stdout:

```text
matches=[1:she#1, 2:he#0, 2:hers#2, 2:he#4]
overlapCount=9
naive oracle=true
```

Automaton có thể tái sử dụng cho nhiều text nếu dictionary không đổi.

## 5. Suffix Array: nhiều query trên một text tĩnh

Suffix bắt đầu tại i là `T[i..n)`. **Suffix Array (SA)** là start index của các suffix được sort theo thứ tự từ điển.

Với `"banana"`, thứ tự là `a(5), ana(3), anana(1), banana(0), na(4), nana(2)`, nên `SA=[5,3,1,0,4,2]`.

Các suffix bắt đầu bằng cùng pattern nằm liền nhau. `lowerBound` tìm suffix đầu tiên không nhỏ hơn pattern; `upperBound` tìm suffix đầu tiên lớn hơn nhóm match.

Comparator suffix–pattern so ký tự; nếu khớp hết pattern thì trả equal vì pattern là prefix của suffix; nếu suffix kết thúc trước pattern thì suffix nhỏ hơn. Đoạn rank `[left,right)` là toàn bộ occurrence. SA sắp theo suffix, không theo vị trí text; nếu cần start tăng dần, sort kết quả. Nếu chỉ cần count, trả `right-left`.

### 5.1. Doubling và complexity

Khởi tạo rank theo ký tự đầu. Với `width=1,2,4,...`, sort suffix theo `(rank[i],rank[i+width])`; phần vượt cuối text dùng sentinel `−1`. Nén các cặp khác nhau thành rank mới.

Bản Java dùng `Integer[]` và comparator sort: O(log n) vòng, mỗi vòng O(n log n), tổng **O(n log² n)** build và O(n) bộ nhớ phụ. Với pattern dài m, k kết quả, query O(m log n + k log k) nếu trả vị trí tăng dần. Build một lần cho text tĩnh; text đổi thì index cũ mất hiệu lực.

### 5.2. Java 17 — SuffixArrayManyQueriesDemo

Lưu file **SuffixArrayManyQueriesDemo.java**:

```java
import java.util.Arrays;

public class SuffixArrayManyQueriesDemo {
    static final class SuffixIndex {
        final String text;
        final int[] suffixArray;

        SuffixIndex(String text) {
            if (text == null) throw new IllegalArgumentException("Null text");
            this.text = text;
            suffixArray = build(text);
        }

        private static int[] build(String text) {
            int n = text.length();
            Integer[] order = new Integer[n];
            int[] rank = new int[n];
            for (int i = 0; i < n; i++) {
                order[i] = i;
                rank[i] = text.charAt(i);
            }
            int width = 1;
            while (width < n) {
                final int step = width;
                final int[] old = rank;
                Arrays.sort(order, (a, b) -> {
                    int cmp = Integer.compare(old[a], old[b]);
                    if (cmp != 0) return cmp;
                    int x = a + step < n ? old[a + step] : -1;
                    int y = b + step < n ? old[b + step] : -1;
                    return Integer.compare(x, y);
                });
                int[] next = new int[n];
                int cls = 0;
                next[order[0]] = 0;
                for (int i = 1; i < n; i++) {
                    int a = order[i - 1], b = order[i];
                    int ax = a + step < n ? rank[a + step] : -1;
                    int bx = b + step < n ? rank[b + step] : -1;
                    if (rank[a] != rank[b] || ax != bx) cls++;
                    next[b] = cls;
                }
                rank = next;
                if (cls == n - 1 || width >= n - width) break;
                width *= 2;
            }
            int[] result = new int[n];
            for (int i = 0; i < n; i++) result[i] = order[i];
            return result;
        }

        private int compare(int start, String p) {
            int limit = Math.min(text.length() - start, p.length());
            for (int i = 0; i < limit; i++) {
                int cmp = Character.compare(text.charAt(start + i), p.charAt(i));
                if (cmp != 0) return cmp;
            }
            return limit == p.length() ? 0 : -1;
        }

        private int bound(String p, boolean upper) {
            int lo = 0, hi = suffixArray.length;
            while (lo < hi) {
                int mid = lo + (hi - lo) / 2;
                int cmp = compare(suffixArray[mid], p);
                if (upper ? cmp > 0 : cmp >= 0) hi = mid;
                else lo = mid + 1;
            }
            return lo;
        }

        int[] findAll(String p) {
            if (p == null || p.isEmpty())
                throw new IllegalArgumentException("Empty pattern");
            int left = bound(p, false), right = bound(p, true);
            int[] out = Arrays.copyOfRange(suffixArray, left, right);
            Arrays.sort(out);
            return out;
        }

        int count(String p) {
            if (p == null || p.isEmpty())
                throw new IllegalArgumentException("Empty pattern");
            return bound(p, true) - bound(p, false);
        }
    }

    static int[] naive(String text, String p) {
        if (text == null || p == null || p.isEmpty())
            throw new IllegalArgumentException("Invalid input");
        int[] buffer = new int[text.length()];
        int size = 0;
        for (int i = 0; i + p.length() <= text.length(); i++)
            if (text.startsWith(p, i)) buffer[size++] = i;
        return Arrays.copyOf(buffer, size);
    }

    public static void main(String[] args) {
        String text = "banana";
        SuffixIndex index = new SuffixIndex(text);
        System.out.println("suffixArray=" + Arrays.toString(index.suffixArray));
        String[] queries = {"ana", "na", "x", "ban", "a"};
        boolean oracle = true;
        for (String p : queries) {
            int[] found = index.findAll(p);
            System.out.printf("query=%s positions=%s%n",
                    p, Arrays.toString(found));
            oracle &= Arrays.equals(found, naive(text, p));
        }
        System.out.println("oracle=" + oracle);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SuffixArrayManyQueriesDemo.java
java SuffixArrayManyQueriesDemo
```

Stdout:

```text
suffixArray=[5, 3, 1, 0, 4, 2]
query=ana positions=[1, 3]
query=na positions=[2, 4]
query=x positions=[]
query=ban positions=[0]
query=a positions=[1, 3, 5]
oracle=true
```

## 6. Chọn thuật toán

| Workload | Lựa chọn | Lý do |
|---|---|---|
| Một pattern, một text | KMP | O(n+m), giữ overlap |
| Một pattern, nhiều text | KMP reuse prefix | Tiền xử lý một lần |
| Nhiều pattern đã biết, một text | Aho–Corasick | Quét text một lượt |
| Cùng dictionary, nhiều text | Reuse Aho automaton | Không build trie lại |
| Một text tĩnh, nhiều query đến sau | Suffix Array | Build index một lần |
| Text thay đổi | Rebuild hoặc index hỗ trợ update | SA tĩnh phụ thuộc text |

KMP k lần trên cùng text quét text k lần. Aho chia sẻ prefix/failure structure, O(S+n+z) kỳ vọng. Khi k nhỏ, KMP nhiều lần có thể đơn giản hơn. Aho phù hợp dictionary biết trước; SA phù hợp text được index trước, query pattern đến sau.

## 7. Kiểm thử và streaming

KMP stream giữ prefix state j qua chunk; Aho stream giữ state automaton và global offset. Reset state ở ranh giới chunk sẽ bỏ match băng qua hai chunk. Suffix Array cần text tĩnh hoàn chỉnh; text đổi thì index cũ không còn hợp lệ.

Test gồm text rỗng, pattern dài hơn text, match đầu/cuối, không match, overlap dày, duplicate ID, suffix pattern (`"he"`/`"she"`), Unicode, empty pattern bị từ chối và nhiều query reuse cùng index.

Differential testing so từng vị trí với naive oracle, không chỉ count. Alphabet nhỏ `{a,b,c}` làm duplicate xuất hiện thường xuyên. Seed cố định giúp tái lập lỗi. Mọi start trả về phải thỏa `text.startsWith(pattern,start)`; vị trí tăng dần; `count(pattern)==findAll(pattern).length`.

## 8. Java 17 — differential harness

Lưu file **TextSearchDifferentialHarness.java** cùng ba file ở trên:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

public class TextSearchDifferentialHarness {
    static String randomString(Random r, int max) {
        int n = r.nextInt(max + 1);
        StringBuilder s = new StringBuilder();
        for (int i = 0; i < n; i++)
            s.append("abc".charAt(r.nextInt(3)));
        return s.toString();
    }

    static String nonEmpty(Random r, int max) {
        String p = randomString(r, max);
        return p.isEmpty() ? "a" : p;
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        Random random = new Random(557);
        for (int t = 0; t < 1200; t++) {
            String text = randomString(random, 24);
            String p = nonEmpty(random, 8);
            check(KmpSinglePatternDemo.findAll(text, p)
                    .equals(KmpSinglePatternDemo.naive(text, p)),
                    "KMP case " + t);
        }
        System.out.println("kmp cases=1200 PASS");

        for (int t = 0; t < 1200; t++) {
            String text = randomString(random, 24);
            int n = 1 + random.nextInt(5);
            List<String> patterns = new ArrayList<>();
            for (int i = 0; i < n; i++)
                patterns.add(nonEmpty(random, 7));
            var actual = new AhoCorasickMultiPatternDemo.Automaton(patterns)
                    .findAll(text);
            var expected = AhoCorasickMultiPatternDemo.naive(text, patterns);
            check(actual.equals(expected), "Aho case " + t);
        }
        System.out.println("aho cases=1200 PASS");

        for (int t = 0; t < 900; t++) {
            String text = randomString(random, 26);
            var index = new SuffixArrayManyQueriesDemo.SuffixIndex(text);
            int n = 1 + random.nextInt(6);
            for (int q = 0; q < n; q++) {
                String p = nonEmpty(random, 8);
                int[] actual = index.findAll(p);
                int[] expected = SuffixArrayManyQueriesDemo.naive(text, p);
                check(Arrays.equals(actual, expected),
                        "Suffix case " + t + " query " + q);
                check(index.count(p) == actual.length,
                        "Count mismatch " + t + " query " + q);
            }
        }
        System.out.println("suffix-array cases=900 PASS");

        String text = "điện thoại";
        check(KmpSinglePatternDemo.findAll(text, "thoại")
                .equals(List.of(5)), "KMP Unicode");
        List<String> patterns = List.of("điện", "thoại");
        var aho = new AhoCorasickMultiPatternDemo.Automaton(patterns);
        check(aho.findAll(text).equals(List.of(
                new AhoCorasickMultiPatternDemo.Match(0, 0),
                new AhoCorasickMultiPatternDemo.Match(5, 1))),
                "Aho Unicode");
        check(Arrays.equals(
                new SuffixArrayManyQueriesDemo.SuffixIndex(text)
                        .findAll("thoại"), new int[] {5}),
                "Suffix Unicode");
        System.out.println("unicode UTF-16 offsets PASS");

        boolean rejected = false;
        try {
            KmpSinglePatternDemo.findAll("abc", "");
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        try {
            new AhoCorasickMultiPatternDemo.Automaton(List.of(""));
            rejected = false;
        } catch (IllegalArgumentException ex) {
            // Expected.
        }
        try {
            new SuffixArrayManyQueriesDemo.SuffixIndex("abc").findAll("");
            rejected = false;
        } catch (IllegalArgumentException ex) {
            // Expected.
        }
        System.out.println("empty pattern rejected=" + rejected);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 KmpSinglePatternDemo.java AhoCorasickMultiPatternDemo.java SuffixArrayManyQueriesDemo.java TextSearchDifferentialHarness.java
java KmpSinglePatternDemo
java AhoCorasickMultiPatternDemo
java SuffixArrayManyQueriesDemo
java TextSearchDifferentialHarness
```

Stdout tổng hợp:

```text
matches=[0, 2]
overlaps=[0, 1, 2]
naive oracle=true
matches=[1:she#1, 2:he#0, 2:hers#2, 2:he#4]
overlapCount=9
naive oracle=true
suffixArray=[5, 3, 1, 0, 4, 2]
query=ana positions=[1, 3]
query=na positions=[2, 4]
query=x positions=[]
query=ban positions=[0]
query=a positions=[1, 3, 5]
oracle=true
kmp cases=1200 PASS
aho cases=1200 PASS
suffix-array cases=900 PASS
unicode UTF-16 offsets PASS
empty pattern rejected=true
```

## 9. Lỗi thường gặp và bài tập

Lỗi phổ biến: bỏ overlap; KMP fallback sai; Aho bỏ terminal suffix/duplicate ID; quên tính z; build lại automaton cho mỗi text; xây SA bằng substring; thiếu sentinel −1; comparator lower/upper bound không nhất quán; chỉ lấy một suffix match; dùng SA sau khi text đổi; nhầm UTF-16 với code point; oracle chỉ so count; không lưu seed.

Bài tập nhanh:

1. `T="ababa"`, `P="aba"` → `[0,2]`.
2. `T="aaaa"`, `P="aa"` → `[0,1,2]`.
3. Prefix function `"ababac"` → `[0,0,1,2,3,0]`.
4. KMP → O(n+m).
5. Aho `"he","she"` khi match `"she"` → báo cả hai.
6. Aho `"a","aa","aaa"` trong `"aaaa"` → 9 occurrence.
7. SA `"banana"` → `[5,3,1,0,4,2]`.
8. Query `"ana"` → `[1,3]`; `"na"` → `[2,4]`; `"a"` → `[1,3,5]`.
9. SA build demo → O(n log² n).
10. Pattern rỗng theo bài → IllegalArgumentException.

Checklist: quy định case/index/Unicode/empty pattern; kiểm overlap, duplicate và suffix pattern; KMP giữ border; Aho BFS failure/output links; SA doubling/sentinel/two bounds; sort vị trí nếu cần; rebuild index khi text đổi; oracle so từng vị trí; test Unicode và seed cố định; tính preprocessing và output memory.

**Tổng kết:** KMP phù hợp một pattern; Aho–Corasick phù hợp dictionary pattern đã biết; Suffix Array phù hợp một text tĩnh với nhiều query đến sau. Chọn theo workload, định nghĩa rõ overlap/duplicate/index và đối chiếu từng vị trí với oracle độc lập.
