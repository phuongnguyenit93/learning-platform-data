# Keeping or discarding trailing empty fields when splitting strings

In the string `"Lan,Java,,"`, the two trailing commas may represent **two empty columns**. Discarding them turns a four-column record into a two-column record. The `limit` rules were covered in the previous lesson; this lesson focuses on **the impact on structured data**, how to validate field counts, and distinguishing empty from blank.

## 1. Never confuse an empty field with a missing field

| Input | `split(",")` | `split(",", -1)` |
| --- | --- | --- |
| `"Lan,Java,,"` | `["Lan", "Java"]` | `["Lan", "Java", "", ""]` |
| `"A,B,"` | `["A", "B"]` | `["A", "B", ""]` |
| `"A,,C,"` | `["A", "", "C"]` | `["A", "", "C", ""]` |
| `",,"` | Array of length 0 | Three `""` elements |
| `""` | One `""` element | One `""` element |

`split(regex)` uses `limit=0`, so **all** trailing empty elements are removed; `split(regex, -1)` keeps them. Leading and middle empty elements remain if they are not part of the removed trailing tail.

When testing empty data, print `parts.length` and the index of each field. `Arrays.toString` does not add quotes around empty strings; looking at `[]` alone makes it easy to confuse an empty array with an array containing one empty element.

## 2. Four-column schema validation example

Save as `PreserveColumnsDemo.java` (JDK 17+):

```java
public class PreserveColumnsDemo {
    public static void main(String[] args) {
        String input = "Lan,Java,,";
        String[] defaultParts = input.split(",");
        String[] fields = input.split(",", -1);

        System.out.println("default=" + defaultParts.length);
        System.out.println("preserved=" + fields.length);
        for (int i = 0; i < fields.length; i++) {
            System.out.println(i + ": [" + fields[i] + "]");
        }
        if (fields.length != 4) {
            throw new IllegalArgumentException("Expected four columns");
        }

        String name = fields[0];
        String language = fields[1];
        String level = fields[2];
        String note = fields[3];
        System.out.println(name + ": " + language);
        System.out.println(level.isEmpty() && note.isEmpty());

        System.out.println(input.equals(String.join(",", fields)));
        System.out.println(input.equals(String.join(",", defaultParts)));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PreserveColumnsDemo.java
java PreserveColumnsDemo
```

```text
default=2
preserved=4
0: [Lan]
1: [Java]
2: []
3: []
Lan: Java
true
true
false
```

With a single-character literal delimiter `","`, `String.join(",", input.split(",", -1))` reconstructs the exact original string including trailing delimiters; the `split(",")` version lost them. Do not generalize this exact-reconstruction property to every regex because a regex can match varying patterns or lengths.

## 3. `""` differs from `" "` and from an absent field

`"A, ,"` with `split(",", -1)` gives `["A", " ", ""]`. The second field contains **a single space**, while the third field has length 0:

```java
String[] fields = "A, ,".split(",", -1);
System.out.println(fields[1].isEmpty()); // false
System.out.println(fields[1].isBlank()); // true
System.out.println(fields[2].isEmpty()); // true
```

`strip()`, `trim()`, or `isBlank()` can be useful when data rules allow whitespace normalization, but they must not be applied unconditionally to data whose original values must be preserved.

The record `"A,B"` has two fields, whereas `"A,B,"` has an existing but empty third field. If the format requires three columns, preserve them with `-1`, verify `parts.length==3`, and only then validate each required value. `split` does not validate schemas automatically.

## 4. Choosing a handling policy

Use `-1` when you need exact column counts, object mapping, data reconstruction, or tracking trailing empty fields. Use the default if the format allows **intentionally omitting** trailing empty parts. For literal delimiters such as `|` or `.`, you can combine `Pattern.quote(delimiter)` with `-1`.

Neither approach is sufficient for reading **quoted CSV**: commas inside quoted fields require a CSV parser. Trailing empty fields are only one of a parser's many requirements.

## Self-check

1. How many parts does `"x,y,,".split(",", -1)` have, and what are the trailing parts?
2. Why does `",,".split(",")` have `length=0` while `"".split(",")` has `length=1`?
3. If you need four columns from `"id,name,note,"`, which overload should you choose?
4. Do the last two fields of `"A, ,"` have the same value?

**Answers:** (1) Four parts; the last two are `""`. (2) An all-delimiter string produces only empty parts, which are all removed; an empty string contains no `,` matches, so it returns itself. (3) `split(",", -1)` and check `length==4`. (4) No; one field contains a space, and the other is empty.

**Remember:** **Preserve empty fields first, validate the schema afterward.**