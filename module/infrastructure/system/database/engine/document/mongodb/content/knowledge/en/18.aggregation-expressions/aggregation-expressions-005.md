# String Processing, Regular Expressions, and Collation Limitations in MongoDB Aggregation

## 1. Lesson Objectives

A MongoDB document often contains many kinds of strings: customer names, order codes, email addresses, notes, classification tags, and free-form user input. When building reports or APIs, applications need to split, concatenate, trim, pattern-match, normalize, or validate these strings directly inside the **aggregation pipeline**.

For example:

- Turn `"  Minh  "` into `"Minh"`.
- Split `"vip, new, priority"` into a clean array of tags.
- Build a `displayName` from multiple fields without letting a `null` value break the concatenation.
- Extract the code `ORD-123` from `"Mã ORD-123, INV-456"`.
- Check whether a name matches the pattern `^lan$` case-insensitively.
- Count and slice Unicode strings with diacritics or emojis without confusing **bytes** with **code points**.
- Understand why a collation with `strength: 1` can treat `cafe` and `café` as equal in equality comparisons, while `$regexMatch` does not.
- Use a collation-aware index for equality comparisons without expecting an accent-ignoring regex to automatically use that index.

This lesson belongs to the **Aggregation Expressions** chapter of the **MongoDB Document Database Engine** module, focusing on **string processing, regular expressions, and collation limitations**.

After this lesson, you will be able to distinguish:

1. String manipulation expressions such as `$concat`, `$split`, `$trim`, `$substrCP`, and `$replaceAll`.
2. Regular expression operators such as `$regexMatch`, `$regexFind`, and `$regexFindAll`.
3. Collation-aware string operations such as `$eq`, `$match`, `$sort`, and `$group`, versus **non-collation-aware** operations.
4. Input data types, missing/null values, Unicode handling, syntax errors, and execution cost.
5. Designing self-contained pipelines in `mongosh`, using them in Compass, and building them with the Java Driver.

**Core principle:** collation is not a Unicode converter or a global switch that makes every string operator case-insensitive and accent-insensitive. Each expression group has its own rules.

## 2. Where Do Aggregation Expressions Live?

An aggregation pipeline reads documents from a collection and passes them through multiple stages:

~~~text
customers collection
       |
       v
     $match             Select documents to process
       |
       v
     $set               Add computed fields
       |
       v
     $project           Select output fields
       |
       v
     $sort              Sort according to operation rules
       |
       v
     Result
~~~

An expression is used in positions such as:

~~~javascript
db.customers.aggregate([
  {
    $set: {
      cleanName: {
        $trim: { input: "$name" }
      }
    }
  },
  {
    $project: {
      _id: 1,
      cleanName: 1
    }
  }
]);
~~~

Distinguish three notations:

| Syntax | Meaning |
|---|---|
| `"$name"` | References the `name` field of the document currently being processed |
| `"$$part"` | References the `part` variable created inside an expression such as `$map` |
| `{ $literal: "$name" }` | Literal string data `"$name"`, not reading a field |

A standard `aggregate()` command only produces a **read result**; `$set` inside a pipeline does not automatically write new data back to the collection. When using similar stages in an update pipeline or adding a write stage such as `$merge`, the write semantics differ.

## 3. Preparing the Practice Database

Use a MongoDB Server/cluster you have access to and open `mongosh`. Only execute write commands on the practice database:

~~~javascript
use aggregation_string_lab
~~~

Load 11 documents to test case sensitivity, diacritics, emojis, missing fields, null, and notes containing codes:

~~~javascript
const sampleCustomers = [
  {
    _id: 1, tenantId: "tenant-A",
    name: "Lan", code: "AB-001",
    email: "lan@example.test",
    note: "Mã ORD-123, INV-456",
    rawTags: "vip, new"
  },
  {
    _id: 2, tenantId: "tenant-A",
    name: "lan", code: "ab-002",
    email: "LAN@example.test",
    note: "ORD-789",
    rawTags: " new ,vip "
  },
  {
    _id: 3, tenantId: "tenant-A",
    name: "LAN", code: "AB-003",
    email: "lan.alt@example.test",
    note: "Không có mã",
    rawTags: ""
  },
  {
    _id: 4, tenantId: "tenant-A",
    name: "cafe", code: "CA-010",
    email: "cafe@example.test",
    note: "Mã ORD-123, INV-456",
    rawTags: "food, sale"
  },
  {
    _id: 5, tenantId: "tenant-A",
    name: "café", code: "CA-011",
    email: "cafe.plus@example.test",
    note: "Mã ORD-456",
    rawTags: "food"
  },
  {
    _id: 6, tenantId: "tenant-A",
    name: "Ánh", code: "VN-100",
    email: "anh.accent@example.test",
    note: "Chào khách",
    rawTags: "vip"
  },
  {
    _id: 7, tenantId: "tenant-A",
    name: "Anh", code: "VN-101",
    email: "Anh@Example.Test",
    note: "Đã giao",
    rawTags: ""
  },
  {
    _id: 8, tenantId: "tenant-A",
    name: "  Minh  ", code: "VN-102",
    email: "minh@example.test",
    note: "REF: ABC-123-XYZ",
    rawTags: " new , vip ,, "
  },
  {
    _id: 9, tenantId: "tenant-B",
    name: "🎉Lan", code: "EM-103",
    email: "emoji@example.test",
    note: "Chào 🎉 bạn",
    rawTags: "event"
  },
  {
    _id: 10, tenantId: "tenant-A",
    name: "Mai", code: "VN-104",
    email: null,
    rawTags: null
    // Intentionally omits the note field
  },
  {
    _id: 11, tenantId: "tenant-B",
    name: "lan-anh", code: "AB-004",
    email: "lan-anh@example.test",
    note: "ORD-001, ORD-002",
    rawTags: "special"
  }
];

sampleCustomers.forEach(customer => {
  db.customers.replaceOne(
    { _id: customer._id },
    customer,
    { upsert: true }
  );
});

db.customers.countDocuments({});
~~~

With an initially empty collection, the last command returns **11**. `replaceOne(..., {upsert:true})` allows reloading by `_id`, and also **resets** the 11 sample documents if they were modified. It does not delete other documents already inserted into the collection.

Quick check:

~~~javascript
db.customers.find(
  {},
  { _id: 1, name: 1, code: 1, rawTags: 1 }
).sort({ _id: 1 });
~~~

Intentional test groups:

- IDs 1, 2, 3: `Lan`, `lan`, `LAN`.
- IDs 4, 5: `cafe` and `café`.
- IDs 6, 7: Vietnamese names with and without diacritics.
- ID 8: leading/trailing whitespace, tags with extra whitespace.
- ID 9: emoji `🎉` occupying multiple UTF-8 bytes.
- ID 10: `email: null`, `rawTags: null`, and **missing** `note`.
- ID 11: name starting with `lan` but not strictly equal to `lan`.

When comparing ID results below, we assume the collection contains only the sample data with no concurrent modifications.

## 4. $concat: Concatenating Strings

### 4.1. Syntax

`$concat` concatenates string expressions in order:

~~~javascript
{
  $concat: [
    <string-expression-1>,
    <string-expression-2>,
    ...
  ]
}
~~~

Example concatenating a prefix with `name`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      label: {
        $concat: [
          "Customer: ",
          "$name"
        ]
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  label: "Customer: Lan"
}
~~~

Values must be compatible with string types. When concatenating numbers or ObjectIds, convert types first according to your data contract.

### 4.2. One null/missing Operand Affects the Entire Concatenation

Try:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 10 } },
  {
    $project: {
      label: {
        $concat: [
          "$name",
          " <",
          "$email",
          ">"
        ]
      }
    }
  }
]);
~~~

Because ID 10 has `email: null`, `$concat` returns `null` for `label`. It does not automatically skip null elements.

Solution using `$ifNull`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 10 } },
  {
    $project: {
      label: {
        $concat: [
          "$name",
          " <",
          { $ifNull: ["$email", "no-email"] },
          ">"
        ]
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  _id: 10,
  label: "Mai <no-email>"
}
~~~

`$ifNull` handles `null` and `missing`; it does not automatically turn non-string BSON types into strings.

### 4.3. Converting Types with $toString

For numeric fields, you can use:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      label: {
        $concat: [
          "ID=",
          { $toString: "$_id" },
          " - ",
          "$name"
        ]
      }
    }
  }
]);
~~~

Result: `"ID=1 - Lan"`.

`$toString` has BSON conversion rules and can throw errors on unsupported types. In pipelines that must tolerate inconsistent data, use `$convert` with appropriate `onError`/`onNull`.

## 5. $trim, $ltrim, and $rtrim

Three expressions remove unwanted characters from the **start/end of a string**:

| Expression | Effect |
|---|---|
| `$trim` | Removes from both ends |
| `$ltrim` | Removes from the left/start |
| `$rtrim` | Removes from the right/end |

### 5.1. Stripping Leading and Trailing Whitespace

~~~javascript
db.customers.aggregate([
  { $match: { _id: 8 } },
  {
    $project: {
      _id: 0,
      before: "$name",
      after: {
        $trim: { input: "$name" }
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  before: "  Minh  ",
  after: "Minh"
}
~~~

`$trim` does not remove whitespace in the **middle** of a string. For example, `"Nguyễn   An"` will still contain multiple spaces between the two words after trimming.

### 5.2. Specifying Exact Characters to Strip

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      cleanedCode: {
        $trim: {
          input: "$code",
          chars: " -"
        }
      }
    }
  }
]);
~~~

`chars` is a set of **characters** allowed to be stripped from the ends, not a substring that must match in exact sequence. With `chars: " -"`, consecutive spaces and hyphens at the start/end can be removed.

If the application needs to remove hyphens **in the middle** of a code, `$trim` is not the right choice; look at `$replaceAll` or another rule.

### 5.3. Missing Data and Data Types

If `input` is null/missing, the trim family may return `null`. If `input` is not a string, the expression can raise a type error. For untrusted API data, use schema validation or type handling before trimming.

A fallback pattern:

~~~javascript
{
  $trim: {
    input: {
      $ifNull: ["$name", ""]
    }
  }
}
~~~

Falling back to `""` is a business decision; it does not imply that a missing field and an empty string always carry the same meaning.

## 6. $split: Splitting a String into an Array

`$split` divides a string using a delimiter:

~~~javascript
{
  $split: [
    <input-string>,
    <delimiter-string>
  ]
}
~~~

Example on ID 1:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      rawTags: 1,
      parts: {
        $split: ["$rawTags", ","]
      }
    }
  }
]);
~~~

Resulting `parts`:

~~~javascript
[
  "vip",
  " new"
]
~~~

The second element still has a leading space. `$split` only **splits**; it does not automatically trim each element.

### 6.1. Splitting and Cleaning Each Element

Use `$map` and `$trim`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 2 } },
  {
    $project: {
      _id: 0,
      tags: {
        $map: {
          input: {
            $split: [
              { $ifNull: ["$rawTags", ""] },
              ","
            ]
          },
          as: "tag",
          in: {
            $trim: { input: "$$tag" }
          }
        }
      }
    }
  }
]);
~~~

Result for ID 2:

~~~javascript
{
  tags: ["new", "vip"]
}
~~~

### 6.2. Removing Empty Elements with $filter

ID 8 has `rawTags: " new , vip ,, "`, so after `$split` and `$trim` there will be empty elements. Add `$filter`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 8 } },
  {
    $project: {
      _id: 0,
      tags: {
        $filter: {
          input: {
            $map: {
              input: {
                $split: [
                  { $ifNull: ["$rawTags", ""] },
                  ","
                ]
              },
              as: "tag",
              in: {
                $trim: { input: "$$tag" }
              }
            }
          },
          as: "tag",
          cond: { $ne: ["$$tag", ""] }
        }
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  tags: ["new", "vip"]
}
~~~

This also works for ID 10 with `rawTags: null`: it falls back to `""`, `$split` yields an empty element, and after `$filter` the final array is `[]`.

### 6.3. Delimiter Is a Literal String

`$split` does not accept a regex as a delimiter. For instance, `","` only splits on commas. If input uses multiple different delimiters, normalize first with `$replaceAll`, combine multiple steps, or handle outside the database.

Both input and delimiter must be strings. If the delimiter does not appear in the input, the result is typically a single-element array containing the original input.

## 7. $strLenBytes and $strLenCP: How Long Is a Unicode String?

For ASCII strings, UTF-8 byte length and code point count are usually equal. For Vietnamese text, emojis, and multi-byte characters, they can differ significantly.

Two expressions:

- `$strLenBytes`: counts **UTF-8 bytes**.
- `$strLenCP`: counts **Unicode code points**.

### 7.1. Example: cafe and café

~~~javascript
db.customers.aggregate([
  { $match: { _id: 5 } },
  {
    $project: {
      _id: 0,
      name: 1,
      bytes: { $strLenBytes: "$name" },
      codePoints: { $strLenCP: "$name" }
    }
  }
]);
~~~

For the string `"café"` containing `é` as a single precomposed code point:

~~~javascript
{
  name: "café",
  bytes: 5,
  codePoints: 4
}
~~~

The three letters `c`, `a`, `f` take one byte each; `é` typically takes two bytes in UTF-8. The code point count is four.

### 7.2. Emoji

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      _id: 0,
      name: 1,
      bytes: { $strLenBytes: "$name" },
      codePoints: { $strLenCP: "$name" }
    }
  }
]);
~~~

For `"🎉Lan"`:

~~~javascript
{
  name: "🎉Lan",
  bytes: 7,
  codePoints: 4
}
~~~

The emoji `🎉` takes 4 UTF-8 bytes but one code point. Complex emoji sequences can consist of **multiple code points yet only one displayed grapheme cluster**. Therefore:

> `$strLenCP` measures code points, not necessarily the number of user-perceived characters (*grapheme clusters*).

This matters greatly when enforcing UI name-length limits. With complex Unicode, code point counts can still differ from visual character counts.

### 7.3. Visually Identical Strings May Not Have the Same Code Points

Unicode can represent an accented letter in precomposed form or as a base character + combining mark. Two visually identical strings may have different code point and byte counts.

`$strLenCP` does not automatically normalize all strings into a single Unicode form. If an application requires strict length rules, design a consistent normalization and validation policy at the input boundary.

## 8. $substrBytes and $substrCP: Slicing Strings in the Right Units

### 8.1. Syntax

~~~javascript
{
  $substrBytes: [
    <string>,
    <start-byte>,
    <byte-count>
  ]
}
~~~

~~~javascript
{
  $substrCP: [
    <string>,
    <start-codepoint>,
    <codepoint-count>
  ]
}
~~~

The two expressions look similar in form, yet differ in position and length units.

### 8.2. Slicing ASCII Strings

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      prefix: {
        $substrCP: ["$code", 0, 2]
      }
    }
  }
]);
~~~

With `code: "AB-001"`, the result is `prefix: "AB"`. When a string is pure ASCII, `$substrBytes` with the same indices generally returns the equivalent result.

### 8.3. Slicing Names Containing Emojis

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      _id: 0,
      firstCodePoint: {
        $substrCP: ["$name", 0, 1]
      },
      firstFourBytes: {
        $substrBytes: ["$name", 0, 4]
      }
    }
  }
]);
~~~

Both can return `"🎉"` on `"🎉Lan"`, yet the index units differ:

- `$substrCP` counts 1 code point.
- `$substrBytes` needs 4 bytes to hold that emoji.

Do not use `$substrBytes: ["$name",0,1]` expecting the whole emoji: slicing into the middle of a multi-byte UTF-8 character is invalid and can cause MongoDB to return an error.

### 8.4. Choosing Bytes or CP?

| Requirement | Consider |
|---|---|
| Protocol formats with UTF-8 byte offsets | `$substrBytes` |
| Extracting a number of Unicode code points | `$substrCP` |
| Displaying "first n user-perceived characters" | Requires grapheme-cluster awareness; `$substrCP` does not solve every emoji/combining mark |
| Pure ASCII SKU codes | Both produce equivalent results, though data-type rules are still needed |
| Unknown whether input contains Unicode | Avoid guessing byte offsets from code point counts |

## 9. $indexOfBytes and $indexOfCP: Finding Substring Positions

Two expressions find the first occurrence index of a substring:

~~~javascript
{
  $indexOfBytes: [
    <string>,
    <substring>
  ]
}
~~~

~~~javascript
{
  $indexOfCP: [
    <string>,
    <substring>
  ]
}
~~~

Beyond the first two arguments, these expressions also support optional start/end bounds when needed. Return values use byte or code point units respectively, returning **-1** when the substring is not found within the search range.

### 9.1. Comparing Offsets on Emoji

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      _id: 0,
      name: 1,
      byteIndex: {
        $indexOfBytes: ["$name", "Lan"]
      },
      codePointIndex: {
        $indexOfCP: ["$name", "Lan"]
      }
    }
  }
]);
~~~

For `"🎉Lan"`:

~~~javascript
{
  name: "🎉Lan",
  byteIndex: 4,
  codePointIndex: 1
}
~~~

`"Lan"` starts after 4 bytes of the emoji, yet after 1 code point. Never mix offsets from `$indexOfCP` into `$substrBytes` or vice versa.

### 9.2. Checking Substring Presence

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      code: 1,
      hasDash: {
        $gte: [
          { $indexOfCP: ["$code", "-"] },
          0
        ]
      }
    }
  }
]);
~~~

`hasDash` is `true` for sample codes containing `-`. If not found, `$indexOfCP` returns `-1`.

### 9.3. Do Not Confuse Substring Search with Regex

`$indexOfCP` searches for substrings via literal matching; it does not understand `[0-9]` or `^ABC` as regular expressions. When patterns are needed, use `$regexMatch`/`$regexFind`.

These literal search operations also do not automatically apply full collation case and accent equivalence rules.

## 10. $toLower, $toUpper, and $strcasecmp

### 10.1. Changing Case

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      code: 1,
      codeUpper: { $toUpper: "$code" },
      codeLower: { $toLower: "$code" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

On ASCII code strings:

~~~text
AB-001 → ab-001 (toLower)
ab-002 → AB-002 (toUpper)
~~~

**Important limitation:** MongoDB documents the behavior of `$toLower`, `$toUpper`, and `$strcasecmp` as **only well-defined for ASCII strings**. Do not build a full Vietnamese name-normalization policy solely on those expressions.

For example, expecting `$toLower` to accurately normalize all accented characters, locale-specific casing rules, or complex Unicode sequences is unsafe as an engineering contract.

### 10.2. Comparing Two Strings with $strcasecmp

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      compareWithLan: {
        $strcasecmp: ["$name", "lan"]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

`$strcasecmp` returns a negative number, `0`, or a positive number corresponding to case-insensitive comparison order per its semantics. For the ASCII strings `Lan`, `lan`, and `LAN`, comparing against `lan` returns `0`.

Do not extrapolate results on accented/complex Unicode strings to assume full Vietnamese collation rules.

### 10.3. When Locale-Aware String Comparison Is Needed

If the requirement is "compare names according to locale, distinguishing accents while ignoring case," use **collation** with corresponding comparison operators such as `$eq` or `$sort`, rather than assuming `$toLower` over arbitrary Unicode yields a complete canonical key.

If you want to store a persistently normalized field, the application needs a Unicode normalization policy, locale control, real-data testing, and maintenance of that field on write.

## 11. $replaceOne and $replaceAll: Replacing Substrings

In **aggregation expressions**, MongoDB provides:

- `$replaceOne`: replaces the **first occurrence** of the search string.
- `$replaceAll`: replaces **all occurrences** of the search string.

Both use the fields:

~~~javascript
{
  $replaceOne: {
    input: <string-expression>,
    find: <string-expression>,
    replacement: <string-expression>
  }
}
~~~

Or replace `$replaceOne` with `$replaceAll`.

### 11.1. Comparing Single vs. All Replacements

~~~javascript
db.customers.aggregate([
  { $match: { _id: 11 } },
  {
    $project: {
      _id: 0,
      original: "$note",
      firstOnly: {
        $replaceOne: {
          input: "$note",
          find: "ORD",
          replacement: "ORDER"
        }
      },
      allMatches: {
        $replaceAll: {
          input: "$note",
          find: "ORD",
          replacement: "ORDER"
        }
      }
    }
  }
]);
~~~

ID 11 has note `"ORD-001, ORD-002"`. Result:

~~~javascript
{
  original: "ORD-001, ORD-002",
  firstOnly: "ORDER-001, ORD-002",
  allMatches: "ORDER-001, ORDER-002"
}
~~~

### 11.2. Do Not Treat Search-and-Replace as Regex

`find` in `$replaceAll` is a literal string, not a regex pattern:

~~~javascript
{
  $replaceAll: {
    input: "ORD-123",
    find: "[0-9]+",
    replacement: "XXX"
  }
}
~~~

This expression does not replace digits with `XXX` via regex; it searches for the literal string `"[0-9]+"`. For pattern-based replacement, design multi-step extraction/reconstruction or handle appropriately in the application layer.

### 11.3. Collation Does Not Govern $replaceOne and $replaceAll

Suppose a query runs with:

~~~javascript
{
  collation: {
    locale: "en",
    strength: 1
  }
}
~~~

Strength 1 treats `cafe` and `café` as equivalent in collation-based equality comparisons. However, `$replaceAll` does not apply that equivalence:

~~~javascript
db.customers.aggregate(
  [
    { $match: { _id: { $in: [4, 5] } } },
    {
      $project: {
        _id: 1,
        name: 1,
        renamed: {
          $replaceAll: {
            input: "$name",
            find: "cafe",
            replacement: "shop"
          }
        }
      }
    },
    { $sort: { _id: 1 } }
  ],
  {
    collation: { locale: "en", strength: 1 }
  }
);
~~~

Expected:

~~~text
ID 4: "cafe" → "shop"
ID 5: "café" → "café" (unchanged)
~~~

Substring search semantics in replacement expressions are case-sensitive and accent-sensitive; they **ignore the operation's collation**. This is one of the core limitations covered in this lesson.

### 11.4. Null/Missing and Input Normalization

If `input`, `find`, or `replacement` is null/missing, replacement expressions can return `null` per their semantics. When a stable string output is needed:

~~~javascript
{
  $replaceAll: {
    input: { $ifNull: ["$note", ""] },
    find: "ORD",
    replacement: "ORDER"
  }
}
~~~

If a field has the wrong BSON type, use schema validation or controlled conversion expressions rather than expecting string replacement to handle arbitrary data types.

## 12. Regular Expressions: Three Key Expressions

MongoDB supports three aggregation expressions for regular expression processing:

| Expression | Result Shape | When to Use |
|---|---|---|
| `$regexMatch` | Boolean | Check whether a string matches a pattern |
| `$regexFind` | First match object or `null` | Extract the first matching substring, index, and capture groups |
| `$regexFindAll` | Array of match objects | Extract all occurrences of a pattern |

All three share the basic structure:

~~~javascript
{
  $regexMatch: {
    input: <string-expression>,
    regex: <pattern>,
    options: <regex-flags>
  }
}
~~~

`regex` can be expressed as a pattern string or a regex literal in supported contexts. `options` is optional; pass it only when flags such as `i` are needed.

### 12.1. Regex Literal in mongosh

~~~javascript
{
  $regexMatch: {
    input: "$name",
    regex: /^lan$/i
  }
}
~~~

### 12.2. Pattern String and Options

~~~javascript
{
  $regexMatch: {
    input: "$name",
    regex: "^lan$",
    options: "i"
  }
}
~~~

Both examples define a pattern anchored at the start of the string, containing `lan`, and ending at the end of the string, case-insensitively via the `i` regex flag.

Do not declare a flag in two conflicting ways (e.g., literal already containing `i` while `options` repeats inconsistently). For Compass JSON or configuration-driven pipelines, the string + options form is usually easier to serialize.

### 12.3. Common Regex Symbols

| Symbol | Meaning |
|---|---|
| `^` | Start of string (or start of line with appropriate flag) |
| `$` | End of string (or end of line with appropriate flag) |
| `[0-9]` | One ASCII digit |
| `[A-Z]` | One uppercase Latin letter in range |
| `+` | One or more |
| `*` | Zero or more |
| `?` | Zero or one, or modifier depending on context |
| `{3}` | Exactly 3 times |
| `(...)` | Grouping and optional capture |
| `a|b` | Either branch |
| `\d` | Digit shorthand per regex engine semantics |
| `i` | Case-insensitive flag |
| `m` | Multiline flag, affects anchors |
| `s` | Dotall flag so `.` matches newlines |
| `x` | Extended mode for patterns when supported |

Do not treat regex as a complete validator for complex standards from a short pattern alone. For instance, validating emails or international phone numbers also involves domain-specific rules.

## 13. $regexMatch: Checking Whether a String Matches a Pattern

### 13.1. Finding Names with a Case-Insensitive Pattern

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      isLan: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

With the sample set:

- `isLan: true` on IDs **1, 2, 3**.
- `isLan: false` on ID **11** because `"lan-anh"` has characters after `lan`.
- ID 9 `"🎉Lan"` does not match a pattern anchored with `^` at the start.
- Other names do not match.

If you omit the trailing `$`:

~~~javascript
{
  $regexMatch: {
    input: "$name",
    regex: "^lan",
    options: "i"
  }
}
~~~

then ID 11 `"lan-anh"` also matches. Thus, **anchors are part of business requirements**, not mere syntax details.

### 13.2. Using Boolean in $match

You can place the expression inside `$expr` to filter documents:

~~~javascript
db.customers.aggregate([
  {
    $match: {
      $expr: {
        $regexMatch: {
          input: { $ifNull: ["$name", ""] },
          regex: "^lan$",
          options: "i"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Result: IDs **1, 2, 3**.

However, placing a regex expression inside `$expr` does not automatically guarantee index usage for name lookups. When the task is simply case-insensitive equality and a matching collation index exists, a collation-aware `$match` equality filter is usually a better design.

### 13.3. Checking Code Format, Not Arbitrary Business Validity

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      code: 1,
      codeLooksValid: {
        $regexMatch: {
          input: "$code",
          regex: "^[A-Z]{2}-[0-9]{3}$"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

All sample codes except ID **2** match two uppercase ASCII letters + hyphen + three digits. ID 2 has `ab-002`, so it fails the case-sensitive pattern.

Adding `options: "i"` accepts `ab-002`. Yet that only validates *shape*, not whether the SKU is valid in business terms or exists in the product catalog.

### 13.4. Null and Wrong-Type Input

ID 10 has `email: null`. Do not assume regex treats `null` as an empty string. Handle it explicitly:

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      hasExampleDomain: {
        $regexMatch: {
          input: {
            $ifNull: ["$email", ""]
          },
          regex: "@example[.]test$",
          options: "i"
        }
      }
    }
  }
]);
~~~

For null/missing, the `""` fallback returns boolean `false`, rather than feeding type-incompatible `null` into the expression.

If `email` is stored as a number or array, `$ifNull` cannot fix that type. When schema is not enforced, use `$type`/`$cond` or an appropriate `$convert` policy.

## 14. $regexFind: Getting the First Match, Position, and Captures

`$regexFind` returns:

~~~javascript
{
  match: <matched-string>,
  idx: <index>,
  captures: [<capture1>, <capture2>, ...]
}
~~~

or `null` when there is no match. `idx` represents the match position in **Unicode code points**, not byte offsets.

### 14.1. Extracting Codes from Notes

ID 1 has `note`:

~~~text
Mã ORD-123, INV-456
~~~

Query:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      firstCode: {
        $regexFind: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      }
    }
  }
]);
~~~

Result shape:

~~~javascript
{
  firstCode: {
    match: "ORD-123",
    idx: 3,
    captures: ["ORD", "123"]
  }
}
~~~

In the given string, the first three code points are `M`, `ã`, and a space; `ORD` starts at index `3` (0-based).

- `match` is the entire matched substring.
- `idx` is the starting position.
- `captures[0]` is the first group `ORD|INV`.
- `captures[1]` is the three digits.

If the regex has no `(...)` groups, `captures` is an empty array; optional groups that did not participate in the match can appear as `null`.

### 14.2. Returning Only the Matched String

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $set: {
      extracted: {
        $regexFind: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      code: "$extracted.match"
    }
  }
]);
~~~

Result: `code: "ORD-123"`.

If no match is found, `$regexFind` returns `null`, so decide clearly how the output field should behave. You can use `$ifNull` or a conditional expression:

~~~javascript
{
  $ifNull: [
    "$extracted.match",
    "KHONG_CO_MA"
  ]
}
~~~

### 14.3. Unicode Index of regexFind

Consider an expression on a string containing an emoji:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      _id: 0,
      found: {
        $regexFind: {
          input: "$name",
          regex: "Lan"
        }
      }
    }
  }
]);
~~~

On `"🎉Lan"`, `found.idx` is **1** code point. If you used `$indexOfBytes: ["$name", "Lan"]`, the byte offset is **4**. The two offsets are not interchangeable when slicing strings.

## 15. $regexFindAll: Getting All Matches

Syntax is nearly identical to `$regexFind`:

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      matches: {
        $regexFindAll: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      }
    }
  }
]);
~~~

On note `"Mã ORD-123, INV-456"`, the result has two elements:

~~~javascript
{
  matches: [
    {
      match: "ORD-123",
      idx: 3,
      captures: ["ORD", "123"]
    },
    {
      match: "INV-456",
      idx: 12,
      captures: ["INV", "456"]
    }
  ]
}
~~~

If no match is found, `$regexFindAll` returns an **empty array**, unlike `$regexFind` which returns `null`.

### 15.1. Extracting Matched Strings as a String Array

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      codes: {
        $map: {
          input: {
            $regexFindAll: {
              input: { $ifNull: ["$note", ""] },
              regex: "(ORD|INV)-([0-9]{3})"
            }
          },
          as: "hit",
          in: "$$hit.match"
        }
      }
    }
  }
]);
~~~

Result:

~~~javascript
{
  codes: ["ORD-123", "INV-456"]
}
~~~

### 15.2. Constructing Documents with Code Kind and Number

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      _id: 0,
      tokens: {
        $map: {
          input: {
            $regexFindAll: {
              input: "$note",
              regex: "(ORD|INV)-([0-9]{3})"
            }
          },
          as: "hit",
          in: {
            full: "$$hit.match",
            kind: {
              $arrayElemAt: ["$$hit.captures", 0]
            },
            number: {
              $arrayElemAt: ["$$hit.captures", 1]
            }
          }
        }
      }
    }
  }
]);
~~~

Illustrative output:

~~~javascript
{
  tokens: [
    {
      full: "ORD-123",
      kind: "ORD",
      number: "123"
    },
    {
      full: "INV-456",
      kind: "INV",
      number: "456"
    }
  ]
}
~~~

`number` is still the string `"123"`, not automatically an integer. If you need an integer for arithmetic, use `$toInt` or `$convert` with error handling.

### 15.3. Counting Occurrences

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      matchCount: {
        $size: {
          $regexFindAll: {
            input: { $ifNull: ["$note", ""] },
            regex: "(ORD|INV)-([0-9]{3})"
          }
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

With the sample dataset:

- IDs 1 and 4 have 2 codes.
- IDs 2 and 5 have 1 code.
- ID 11 has 2 codes.
- The remaining IDs have no codes matching the example pattern.

This is the count of **regex matches** inside the string, not the count of documents in the collection.

## 16. Comparing Regex Expressions with the $regex Query Predicate

Two syntaxes are commonly confused:

### 16.1. Query Predicate in $match

~~~javascript
db.customers.aggregate([
  {
    $match: {
      name: {
        $regex: "^lan$",
        $options: "i"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1
    }
  }
]);
~~~

Here `$regex` is a **query operator**. It selects documents whose `name` matches the pattern and can be evaluated by the query planner in query context.

### 16.2. Aggregation Expression Using $regexMatch

~~~javascript
db.customers.aggregate([
  {
    $match: {
      $expr: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1
    }
  }
]);
~~~

`$regexMatch` is an **aggregation expression returning a boolean**. It can also be used inside `$project`, `$set`, `$cond`, `$filter`, and other supported stages/expressions.

Both forms select IDs **1, 2, 3** on the sample data. However, query planning and index utilization can differ; never assume the two syntaxes always have identical performance.

### 16.3. Choosing the Right Tool for the Goal

| Goal | Choice |
|---|---|
| Select documents where a field matches a regex directly | Query `$regex` inside `$match` |
| Compute a boolean `isValid` field from a pattern | `$regexMatch` |
| Extract the first match with position/captures | `$regexFind` |
| Extract multiple matches | `$regexFindAll` |
| Locale-aware equality comparison without regex | Equality + compatible collation |

If you do not need to extract codes or match complex patterns, do not use regex merely to simulate equality.

## 17. How Does Collation Work in Aggregation?

**Collation** defines how strings are compared and sorted according to language rules. Example:

~~~javascript
{
  locale: "en",
  strength: 2
}
~~~

This makes English comparisons accent-sensitive while ignoring uppercase/lowercase differences for common Latin examples.

### 17.1. Basic Strength Levels

| Setting | General Meaning for Latin Examples |
|---|---|
| `strength: 1` | Generally ignores case and accent differences |
| `strength: 2` | Distinguishes accents, generally ignores case |
| `strength: 3` | Also distinguishes case |

This is a high-level summary, not an exhaustive specification of Unicode/ICU rules. Options such as `caseLevel` and specific locales can alter detailed behavior.

### 17.2. Collation in the aggregate Command

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "lan" } },
    {
      $project: {
        _id: 1,
        name: 1
      }
    },
    { $sort: { _id: 1 } }
  ],
  {
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

With the sample data, the result is IDs **1, 2, 3** because `Lan`, `lan`, and `LAN` are equivalent under this configuration.

If the collection has the default simple collation and the operation specifies no collation:

~~~javascript
db.customers.aggregate([
  { $match: { name: "lan" } }
]);
~~~

then equality only selects ID **2**. That difference comes from the comparison rules, not because MongoDB rewrote the names.

### 17.3. Strength 1 and 2 with Accents

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "cafe" } },
    { $project: { _id: 1, name: 1 } },
    { $sort: { _id: 1 } }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

With the `cafe`/`café` example, strength 1 returns IDs **4, 5**.

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "cafe" } },
    { $project: { _id: 1, name: 1 } },
    { $sort: { _id: 1 } }
  ],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Strength 2 distinguishes accents, so only ID **4** matches in the sample set.

Do not generalize from this pair that all letter and accent variants across all languages follow identical equivalence rules.

### 17.4. Collation Affects $eq

You can use an aggregation comparison expression:

~~~javascript
db.customers.aggregate(
  [
    {
      $project: {
        _id: 1,
        name: 1,
        equalsLan: {
          $eq: ["$name", "lan"]
        }
      }
    },
    { $sort: { _id: 1 } }
  ],
  { collation: { locale: "en", strength: 2 } }
);
~~~

With this configuration, `equalsLan` is `true` for `Lan`, `lan`, and `LAN` under collation semantics. This is an example of a string comparison expression, unlike regex operators which have their own rules.

### 17.5. Collation Affects $sort and $group

~~~javascript
db.customers.aggregate(
  [
    {
      $group: {
        _id: "$name",
        count: { $sum: 1 },
        ids: { $push: "$_id" }
      }
    },
    { $sort: { _id: 1 } }
  ],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Variants `Lan/lan/LAN` are grouped together because `$group` uses string comparison rules according to the operation's collation.

The representative `_id` for the group should not be relied upon as a case-normalized canonical display value with a fixed contract. If the application needs a canonical value, define explicit normalization rules.

Similarly, `$sort` by `name` with collation can produce a different order than simple binary sorting. When paginating on locale-aware strings, add a unique tie-breaker key for stable ordering.

### 17.6. At What Scope Is Collation Declared?

An `aggregate` operation generally has **one collation applying to the entire command**, not an arbitrary collation per field or stage.

If a collection has a default collation, operations that do not override it inherit that default. Indexes can also inherit or specify their own collation.

To inspect:

~~~javascript
db.getCollectionInfos({ name: "customers" });
db.customers.getIndexes();
~~~

In this practice lab, the collection was created implicitly by write commands without specifying a custom default collation, so examples without explicit collation use the fresh environment's simple default.

## 18. Core Limitation: Regex Ignores Collation

The aggregation regex expressions:

- `$regexMatch`.
- `$regexFind`.
- `$regexFindAll`.

are **not collation-aware:** they ignore collation string comparison rules. They use regular expression semantics and declared regex flags.

### 18.1. Comparing Equality vs. Regex on cafe/café

Equality with strength 1:

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "cafe" } },
    { $project: { _id: 1, name: 1 } }
  ],
  {
    collation: {
      locale: "en",
      strength: 1
    }
  }
);
~~~

Returns both ID **4** (`cafe`) and **5** (`café`).

However:

~~~javascript
db.customers.aggregate(
  [
    {
      $project: {
        _id: 1,
        name: 1,
        matchesPattern: {
          $regexMatch: {
            input: "$name",
            regex: "^cafe$",
            options: "i"
          }
        }
      }
    }
  ],
  {
    collation: {
      locale: "en",
      strength: 1
    }
  }
);
~~~

`matchesPattern` is `true` for `"cafe"` (ID 4) and `false` for `"café"` (ID 5). The regex `i` flag handles case differences within the regex engine; it **does not mean ignoring accents** like collation strength 1 in this example.

### 18.2. RegexFind Does Not Strip Accents Either

~~~javascript
db.customers.aggregate(
  [
    { $match: { _id: 5 } },
    {
      $project: {
        _id: 0,
        found: {
          $regexFind: {
            input: "$name",
            regex: "cafe"
          }
        }
      }
    }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

`found` does not match literal `"cafe"` inside `"café"`. Setting strength 1 does not turn `$regexFind` into a locale-aware equality comparison.

### 18.3. Same for RegexFindAll

Likewise:

~~~javascript
{
  $regexFindAll: {
    input: "$name",
    regex: "cafe",
    options: "i"
  }
}
~~~

does not treat `café` as `cafe` merely because the operation specifies an accent-insensitive collation.

### 18.4. Query $regex Has the Same Collation Caveat

`$regex` in a query predicate is not collation-aware in the way equality or sorting uses ICU collation. Adding collation strength 1 to `{ name: { $regex: "^cafe$" } }` does not mean it will match every accented variant.

If the requirement is **collation-based equality**, use equality with a compatible collation; do not replace it with regex just for "flexibility."

## 19. Which String Expressions Depend on Collation?

This is a critical question to avoid applying one blanket rule to all expressions:

| Group | Examples | What to Understand About Collation |
|---|---|---|
| String comparison & sorting | `$eq`, equality in `$match`, `$sort`, `$group` | Uses the operation's collation in supported contexts |
| Regex expressions | `$regexMatch`, `$regexFind`, `$regexFindAll` | Ignores collation; uses regex and regex options |
| Substring replacement | `$replaceOne`, `$replaceAll` | Ignores collation; literal character-sensitive matching |
| Substring index lookup | `$indexOfBytes`, `$indexOfCP` | Do not treat as locale-aware equality |
| String splitting | `$split` | Splits by literal string delimiter, not locale-aware regex |
| Length / slicing | `$strLenBytes`, `$strLenCP`, `$substrBytes`, `$substrCP` | Operates in byte or code point units; does not normalize by collation |
| Case conversion | `$toLower`, `$toUpper` | Does not replace locale-aware comparison; note ASCII limitation |
| Expression-specific case-insensitive comparison | `$strcasecmp` | Note behavior is well-defined only for ASCII |

Do not infer that "all of aggregation respects collation" uniformly. Determine precisely whether an expression has locale-aware comparison semantics or dedicated regex/literal/byte semantics.

## 20. Collation-Aware Indexes and Regex Optimization Limits

### 20.1. Creating an Index for Case-Insensitive Equality

~~~javascript
db.customers.createIndex(
  { name: 1 },
  {
    name: "idx_name_en_strength2",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Query:

~~~javascript
db.customers.find({
  name: "lan"
})
.collation({
  locale: "en",
  strength: 2
})
.explain("executionStats");
~~~

The index above has compatible semantics with the query's string comparison. MongoDB **can** use it when the planner determines it is beneficial.

If a query omits collation on a simple-collation collection:

~~~javascript
db.customers.find({
  name: "lan"
}).explain("executionStats");
~~~

then the query and the strength-2 index do not share the same string-equality semantics. Distinguish **correctness of results** from **efficient index utilization**.

### 20.2. Why Doesn't Case-Insensitive Regex Automatically Benefit from This Index?

~~~javascript
db.customers.find({
  name: {
    $regex: "^lan$",
    $options: "i"
  }
}).collation({
  locale: "en",
  strength: 2
}).explain("executionStats");
~~~

A case-insensitive index with collation strength 2 **does not automatically optimize** `$regex` with the `i` flag efficiently. Regex is not collation-aware in the way locale-aware string indexes are structured.

A case-sensitive prefix regex can sometimes leverage an index under simple collation in suitable situations. That is very different from assuming a locale-aware case-insensitive index accelerates arbitrary `/i` regexes.

### 20.3. Regex Expressions Inside $expr Also Need Separate Measurement

~~~javascript
db.customers.aggregate([
  {
    $match: {
      $expr: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  }
]);
~~~

Filtering with an expression can force the server to evaluate the regex across many documents. Do not assume the query planner converts this test into an equality lookup using the collation index.

### 20.4. Inspecting explain

~~~javascript
db.customers.find({
  name: "lan"
})
.collation({
  locale: "en",
  strength: 2
})
.explain("executionStats");
~~~

Monitor:

- `winningPlan`.
- `IXSCAN` or `COLLSCAN`.
- `indexName`.
- `indexBounds`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.

With 11 documents, the planner may choose a collection scan because the dataset is tiny. Do not conclude an index is broken merely because it wasn't selected in a tiny test.

### 20.5. When to Consider Other Search Tools?

Requirements such as natural-language search, autocomplete, fuzzy matching, diverse diacritics, tokenization, or large-scale pattern matching can exceed the scope of equality indexes and simple regexes.

Consider designing a canonical search field by contract, text search, or a dedicated search solution matching your infrastructure and requirements. Do not assume adding the `i` flag to a regex is enough to build an effective multilingual search engine.

## 21. Unicode Data and Normalization Limits

### 21.1. Accented Characters and Normalization Forms

Visually identical `é` can be represented as:

~~~text
Precomposed form:       U+00E9
Decomposed form:        U+0065 + U+0301
~~~

Some collation-based comparisons can handle these equivalences according to Unicode/locale rules. However, expressions operating on **literal substrings**, regexes, or code points must not be assumed to automatically normalize all visually identical forms.

For example:

~~~javascript
{
  $replaceAll: {
    input: "$name",
    find: "é",
    replacement: "e"
  }
}
~~~

must not be treated as a full normalization solution for Vietnamese text or all Unicode combining diacritics.

### 21.2. Do Not Treat Lowercase as Accent Normalization

Even when an expression converts uppercase to lowercase, it does not automatically strip accents, tokenize words, perform transliteration, or apply all locale rules.

A system that needs to match `"Ánh"` when a user types `"anh"` must clarify:

- Does business logic genuinely want accent-insensitive matching?
- By which rules are names normalized?
- Must original data be preserved for display?
- Do rules change for other locales?
- Which index supports the chosen search expression?
- Is there a risk of two distinct names colliding as duplicates?

### 21.3. Choosing the Right Length Unit

| Information | Appropriate Tool |
|---|---|
| UTF-8 bytes | `$strLenBytes` |
| Unicode code points | `$strLenCP` |
| Byte position | `$indexOfBytes` |
| Code point position | `$indexOfCP` |
| Slice by bytes | `$substrBytes` |
| Slice by code points | `$substrCP` |
| Regex match index | `$regexFind.idx` is in code points |
| User-perceived characters | Requires grapheme-cluster semantics; do not assume code points |

Avoid mixing these units within a single Unicode string-slicing pipeline.

## 22. Building a Practical Pipeline: Cleaning, Extracting Codes, and Formatting Output

Example building a report for `tenant-A`:

- Strip whitespace from names.
- Split tags into a trimmed array with empty items removed.
- Validate whether codes match two uppercase Latin letters + `-` + three digits.
- Extract all order/invoice codes from notes.
- Return only the permitted display fields.

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenantId: "tenant-A"
    }
  },
  {
    $set: {
      cleanName: {
        $trim: {
          input: { $ifNull: ["$name", ""] }
        }
      },
      cleanedTags: {
        $filter: {
          input: {
            $map: {
              input: {
                $split: [
                  { $ifNull: ["$rawTags", ""] },
                  ","
                ]
              },
              as: "tag",
              in: {
                $trim: {
                  input: "$$tag"
                }
              }
            }
          },
          as: "tag",
          cond: {
            $ne: ["$$tag", ""]
          }
        }
      },
      codeIsValid: {
        $regexMatch: {
          input: { $ifNull: ["$code", ""] },
          regex: "^[A-Z]{2}-[0-9]{3}$"
        }
      },
      extractedCodes: {
        $map: {
          input: {
            $regexFindAll: {
              input: { $ifNull: ["$note", ""] },
              regex: "(ORD|INV)-([0-9]{3})"
            }
          },
          as: "hit",
          in: "$$hit.match"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      cleanName: 1,
      code: 1,
      codeIsValid: 1,
      cleanedTags: 1,
      extractedCodes: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

A few results to verify:

| ID | cleanName | codeIsValid | cleanedTags | extractedCodes |
|---|---|---|---|---|
| 1 | Lan | true | `["vip","new"]` | `["ORD-123","INV-456"]` |
| 2 | lan | false | `["new","vip"]` | `["ORD-789"]` |
| 3 | LAN | true | `[]` | `[]` |
| 4 | cafe | true | `["food","sale"]` | `["ORD-123","INV-456"]` |
| 5 | café | true | `["food"]` | `["ORD-456"]` |
| 8 | Minh | true | `["new","vip"]` | `[]` |
| 10 | Mai | true | `[]` | `[]` |

The pipeline does not lowercase original data or mutate fields on the server. It only returns shaped output documents.

### 22.1. If You Only Want Documents with Valid Codes

Because `codeIsValid` was created in `$set`, you can add:

~~~javascript
{
  $match: { codeIsValid: true }
}
~~~

**after** `$set` and before `$project`. If you need to filter directly by regex on `code` at the start of the pipeline, you can use the `$regex` query predicate inside `$match`. Which is better depends on whether the boolean value is needed in the output and on the query plan.

### 22.2. If You Want to Sort Names by Locale

~~~javascript
db.customers.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    { $project: { _id: 1, name: 1 } },
    { $sort: { name: 1, _id: 1 } }
  ],
  {
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

This is a collation-aware sort, not regex. On real person names, confirm the locale and expected sort order, and use `_id` as a tie-breaker for pagination.

Do not infer from `vi` locale sort results that `$toLower`, regex, or replacement operations will also follow Vietnamese ordering/semantics.

## 23. Performance Optimization and Constraining Input Regexes

### 23.1. Regex Can Be Very Expensive

A regex expression executed across a large number of documents can consume heavy CPU. Complex patterns, ambiguous repetitions, and long inputs can trigger **catastrophic backtracking** or long processing times.

Be especially cautious when allowing users to supply arbitrary patterns.

Best practices:

1. Limit pattern length and input length.
2. Restrict patterns to a controlled set whenever possible.
3. Never interpolate raw user input into complex regexes without escaping control characters.
4. Identify the real requirement: equality, prefix, full-text, or extraction.
5. Narrow down documents using selective conditions and appropriate indexes before running regex per value.
6. Measure latency and monitor slow queries.
7. Consider execution time limits and semantically sound fallbacks.

Regex is not the only solution for every string search requirement.

### 23.2. Do Not Let a Missing Field Break the Pipeline

String expressions usually require string or properly typed array inputs. Null/missing/wrong-type data can return `null` or raise errors depending on the operator.

Safe regex example:

~~~javascript
{
  $regexMatch: {
    input: {
      $cond: [
        { $eq: [{ $type: "$note" }, "string"] },
        "$note",
        ""
      ]
    },
    regex: "ORD-[0-9]{3}"
  }
}
~~~

Here, if `note` is not a string, the expression uses `""`, avoiding passing numbers, arrays, or `null` into the regex. If the application needs to distinguish data errors from "no match," retain an additional `noteType` field for diagnostics.

### 23.3. Keep Tenant Filters in Both Query and Results

A customer analytics pipeline might only need names and codes, yet it must still filter within the authorized scope:

~~~javascript
{
  $match: {
    tenantId: "tenant-A"
  }
}
~~~

Dropping `tenantId` in `$project` does not ensure only `tenant-A` data was read; filter at the start of the pipeline and enforce authorization at the application/database layers.

### 23.4. When to Run Explain?

~~~javascript
db.customers.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      matches: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  }
]);
~~~

Inspect `winningPlan`, scanned document counts, and related stages provided by the server. A tenant index may be needed for production workloads, though you should never create indexes solely based on 11 sample documents and assume production is tuned.

## 24. MongoDB Compass: Using Expressions and Collation

MongoDB Compass provides an **Aggregations** view for adding stages. Button names and Options panels may vary by version.

Recommended steps:

1. Connect Compass to the server hosting `aggregation_string_lab.customers`.
2. Open the `customers` collection and the **Aggregations** tab.
3. Add a `$match` stage filtering `tenant-A`:

   ~~~json
   {"tenantId":"tenant-A"}
   ~~~

4. Add a `$project` stage with a trim expression:

   ~~~json
   {
     "_id":1,
     "name":1,
     "cleanName":{"$trim":{"input":"$name"}}
   }
   ~~~

5. Run and observe ID 8 changing from `"  Minh  "` to `"Minh"` in the output.
6. Test `$regexMatch`:

   ~~~json
   {
     "_id":1,
     "name":1,
     "isLan":{
       "$regexMatch":{
         "input":"$name",
         "regex":"^lan$",
         "options":"i"
       }
     }
   }
   ~~~

7. Test `$regexFindAll` on `note` to extract codes.
8. If the UI supports **Collation** settings for aggregation, set `{"locale":"en","strength":1}` and compare `cafe`/`café` equality against `$regexMatch`.
9. If no collation option is visible, use `mongosh` to pass the second options object to `aggregate(...)` instead of guessing from the UI.
10. Afterward, switch back to the Documents tab to verify that read-only aggregation did not modify source data.

Some Compass versions require selecting the stage name (`$project`) separately and entering only the stage body into the editor. In that case, do not nest `{"$project":...}` inside the stage body box.

## 25. Java Driver: Building String-Processing Pipelines

In the MongoDB Java Driver, aggregation pipelines can be built using BSON `Document` objects. The following example illustrates the query logic; `database` must be a connected `MongoDatabase`.

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

MongoCollection<Document> customers =
    database.getCollection("customers");

Document normalizedName = new Document(
    "$trim",
    new Document(
        "input",
        new Document("$ifNull", Arrays.asList("$name", ""))
    )
);

Document regexMatch = new Document(
    "$regexMatch",
    new Document("input", "$code")
        .append("regex", "^[A-Z]{2}-[0-9]{3}$")
);

List<Document> pipeline = Arrays.asList(
    new Document("$match",
        new Document("tenantId", "tenant-A")),

    new Document("$project",
        new Document("_id", 1)
            .append("name", 1)
            .append("cleanName", normalizedName)
            .append("code", 1)
            .append("codeIsValid", regexMatch))
);

List<Document> result = customers.aggregate(pipeline)
    .into(new ArrayList<>());

for (Document item : result) {
    System.out.println(item.toJson());
}
~~~

### 25.1. Specifying Collation for Aggregation

~~~java
import com.mongodb.client.model.Collation;
import com.mongodb.client.model.CollationStrength;

Collation caseInsensitive = Collation.builder()
    .locale("en")
    .collationStrength(CollationStrength.SECONDARY)
    .build();

List<Document> result = customers.aggregate(
    Arrays.asList(
        new Document("$match", new Document("name", "lan")),
        new Document("$project",
            new Document("_id", 1).append("name", 1))
    )
).collation(caseInsensitive)
 .into(new ArrayList<>());
~~~

With the sample collection, equality on `name` at strength 2 selects IDs **1, 2, 3**.

**Do not confuse:** `.collation(caseInsensitive)` does not make `$regexMatch` or `$regexFind` inside the pipeline ignore accents or apply locale matching. Regex has its own semantics.

### 25.2. Avoid Passing Untrusted Patterns Directly into the Pipeline

If an API accepts a user keyword and the goal is to **search for a literal string**, ensure special characters such as `.`, `*`, `?`, `[`, and `(` are escaped when used in regex. Building a BSON `Document` avoids naive JSON string concatenation, yet **does not automatically bound regex cost** or validate pattern safety.

When business logic really needs case-insensitive equality, an equality check with an appropriate collation and matching index is simpler and easier to control.

## 26. Common Errors and Misconceptions

| Symptom | Cause | How to Handle |
|---|---|---|
| `$concat` returns null | One component is null/missing | Use `$ifNull` on fields needing fallback |
| `$concat` rejects numbers | Operand is not a string | `$toString` or `$convert` with error handling |
| `$trim` does not remove spaces between words | Trim only strips ends | Use another normalization rule for internal whitespace |
| `$split` leaves leading spaces on items | Split does not auto-trim | `$map` + `$trim` |
| Tags contain empty elements | Adjacent delimiters or empty input | `$filter` out empty strings |
| `$size`/`$map` throws type error | Input is not an array | `$isArray` or schema validation |
| `$strLenBytes` differs from `$strLenCP` | Multi-byte UTF-8 | Choose the right unit |
| `$substrBytes` errors on emoji | Slicing mid-UTF-8 byte sequence | Use `$substrCP` or valid byte offsets |
| Match index from `regexFind` fails with `substrBytes` | `idx` counts code points | Use `$substrCP` to match units |
| `$indexOfCP` returns -1 | Substring not found | Check before using offset |
| `$regexFind` returns null | No match | `$ifNull` or null handling |
| `$regexFindAll` returns `[]` | No match | This is a valid state |
| `$regexMatch` rejects null | Type-incompatible input | `$ifNull` or `$type` check |
| Pattern `^lan$` does not match `lan-anh` | Has end anchor | Remove `$` if prefix match is wanted, after confirming requirements |
| Regex with `i` still misses `café` when searching `cafe` | Case-insensitive does not mean accent-insensitive | Use equality + collation for locale equality |
| Collation strength 1 does not affect regex | Regex expressions ignore collation | Use regex options or suitable search design |
| `$replaceAll` does not replace `café` when finding `cafe` | Literal replacement ignores collation | Normalize intentionally or use the right comparison |
| CI index does not speed up `/i` regex as expected | Regex is not collation-aware | Use equality + collation/index or a search engine |
| `$toLower` does not normalize Unicode names as expected | Behavior only well-defined for ASCII | Define Unicode policy in application |
| `$group` merges names with different casing | Collation treats strings as equivalent | Pick suitable strength; do not treat group key as auto-canonical |
| Count and paginated page have different result sets | Inconsistent filters/collation/conditions | Use identical scope and collation |
| Pipeline is very slow with complex regex | Backtracking, scanning many documents | Limit patterns/inputs, filter early, benchmark workload |
| Aggregate output is right, yet database didn't change | Read pipeline does not write | Use a write API if persistence is required |

## 27. Practice Exercises

Exercises use the 11-document dataset from section 3.

### Exercise 1. Cleaning Names

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      before: "$name",
      after: {
        $trim: { input: "$name" }
      }
    }
  },
  { $match: { _id: 8 } }
]);
~~~

**Expected:** `before: "  Minh  "` and `after: "Minh"`. Explain why `$trim` is not regex and does not automatically normalize accents.

### Exercise 2. Concatenating Labels and Handling null

~~~javascript
db.customers.aggregate([
  { $match: { _id: 10 } },
  {
    $project: {
      label: {
        $concat: [
          "$name",
          " <",
          { $ifNull: ["$email", "unknown"] },
          ">"
        ]
      }
    }
  }
]);
~~~

**Expected:** `"Mai <unknown>"`. What happens if `$ifNull` is removed?

### Exercise 3. Normalizing Tags

Use `$split`, `$map`, `$trim`, and `$filter` on ID 8.

**Expected:** `["new","vip"]`. Why is `$split` alone insufficient?

### Exercise 4. Unicode Bytes and Code Points

~~~javascript
db.customers.aggregate([
  { $match: { _id: 9 } },
  {
    $project: {
      name: 1,
      byteLength: { $strLenBytes: "$name" },
      cpLength: { $strLenCP: "$name" },
      startBytes: {
        $indexOfBytes: ["$name", "Lan"]
      },
      startCP: {
        $indexOfCP: ["$name", "Lan"]
      }
    }
  }
]);
~~~

**Expected:** `byteLength:7`, `cpLength:4`, `startBytes:4`, `startCP:1`.

### Exercise 5. Regex Boolean

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      matched: {
        $regexMatch: {
          input: "$name",
          regex: "^lan$",
          options: "i"
        }
      }
    }
  },
  { $match: { matched: true } },
  { $sort: { _id: 1 } }
]);
~~~

**Expected IDs:** 1, 2, 3. If the pattern changes to `^lan`, which ID is added?

### Exercise 6. Regex Code Extraction

~~~javascript
db.customers.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      first: {
        $regexFind: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      },
      all: {
        $regexFindAll: {
          input: "$note",
          regex: "(ORD|INV)-([0-9]{3})"
        }
      }
    }
  }
]);
~~~

**Expected:** `first.match = "ORD-123"`, `first.idx = 3`, and `all` has 2 elements: `ORD-123` and `INV-456`.

### Exercise 7. Counting Matches per Customer

Use `$size` combined with `$regexFindAll` to compute `matchCount` from `note`. For ID 10 missing `note`, avoid errors using `$ifNull`.

**Expected:** IDs 1, 4, 11 have 2 matches; IDs 2, 5 have 1; remaining IDs have 0.

### Exercise 8. Replacing Once vs. All Occurrences

~~~javascript
db.customers.aggregate([
  { $match: { _id: 11 } },
  {
    $project: {
      first: {
        $replaceOne: {
          input: "$note",
          find: "ORD",
          replacement: "ORDER"
        }
      },
      all: {
        $replaceAll: {
          input: "$note",
          find: "ORD",
          replacement: "ORDER"
        }
      }
    }
  }
]);
~~~

**Expected:** `first` replaces only the first `ORD`; `all` replaces both.

### Exercise 9. Collation Equality Differs from Regex

Run:

~~~javascript
db.customers.aggregate(
  [
    { $match: { name: "cafe" } },
    { $project: { _id: 1, name: 1 } }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

Then try:

~~~javascript
db.customers.aggregate(
  [
    {
      $project: {
        _id: 1,
        name: 1,
        matched: {
          $regexMatch: {
            input: "$name",
            regex: "^cafe$",
            options: "i"
          }
        }
      }
    },
    { $match: { matched: true } }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

**Expected:** Equality selects IDs 4 and 5, whereas regex only selects ID 4. Explain precisely why.

### Exercise 10. Collation Does Not Make replaceAll Ignore Accents

On IDs 4 and 5, use `$replaceAll` to find `"cafe"` and replace it with `"shop"`. Set collation `locale:"en", strength:1` on the operation.

**Expected:** ID 4 changes to `"shop"` in the output; ID 5 keeps `"café"`.

### Exercise 11. Comparing $eq with $strcasecmp

Use `$eq: ["$name", "lan"]` with collation strength 2 to compare the three `Lan` variants. Then use `$strcasecmp` on the corresponding ASCII strings.

**Explanation:** Both approaches may agree that those three ASCII strings are case-equivalent, yet `$strcasecmp` is not a substitute for all collation rules on accented Unicode names.

### Exercise 12. Regex Validating Code Format

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      code: 1,
      validCode: {
        $regexMatch: {
          input: "$code",
          regex: "^[A-Z]{2}-[0-9]{3}$"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Expected:** ID 2 fails to match because `ab-002` has lowercase letters; the remaining codes match the shape. Adding the `i` flag allows ID 2 to match the pattern.

### Exercise 13. Making the Pipeline Tolerant of missing/null

Produce output `noteCodes` as an array of all codes from `note`, even when `note` is null or missing:

~~~javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      noteCodes: {
        $map: {
          input: {
            $regexFindAll: {
              input: { $ifNull: ["$note", ""] },
              regex: "(ORD|INV)-([0-9]{3})"
            }
          },
          as: "hit",
          in: "$$hit.match"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Expected:** ID 10 has `noteCodes: []` without failing the pipeline.

### Exercise 14. Comparing Performance

Create the collation index from section 20 and inspect `explain` for:

1. Equality `name: "lan"` with `en/strength:2`.
2. Regex `^lan$` with `options: "i"`.

Comment on `IXSCAN`/`COLLSCAN`, keys/docs examined, and the limitations of an 11-document test. Do not treat the existence of a case-insensitive index as proof that all regexes are accelerated.

### Exercise 15. Designing a Search API by Requirement

| Requirement | First Option to Consider |
|---|---|
| Names must match equally by English rules, ignoring case | Equality + collation strength 2 + compatible index |
| Names must compare ignoring accents | Collation with appropriate strength, tested on real data |
| Find `ORD-123` code in note | `$regexFind` |
| Extract all codes in note | `$regexFindAll` + `$map` |
| Check only whether note contains a code | `$regexMatch` |
| Split simple CSV tags string | `$split`, `$map`, `$trim`, `$filter` |
| Count UTF-8 bytes | `$strLenBytes` |
| Count code points | `$strLenCP` |
| Sort names by language rules | `$sort` with appropriate collation |
| Free-text, fuzzy, or large multilingual search | Dedicated search design and benchmarking |

## 28. Summary

MongoDB Aggregation provides many string-processing expressions, yet you should choose tools based on **operation semantics**:

- **Concatenate/split/clean:** `$concat`, `$split`, `$trim`, `$ltrim`, `$rtrim`.
- **Length/position/slice:** `$strLenBytes`/`$strLenCP`, `$indexOfBytes`/`$indexOfCP`, `$substrBytes`/`$substrCP`. Always keep byte vs. code point units consistent.
- **Literal substring replacement:** `$replaceOne` and `$replaceAll`; not regex replacement, and does not apply collation to ignore accents/case.
- **Regex:** `$regexMatch` returns boolean; `$regexFind` returns first match; `$regexFindAll` returns all matches. They are not collation-aware.
- **Language-aware comparison/sorting:** `$eq`, equality `$match`, `$sort`, and `$group` use collation where supported. Choose compatible locale, strength, and indexes.
- **Unicode:** `$toLower`/`$toUpper`/`$strcasecmp` do not replace multilingual Unicode normalization policies; `$strLenCP` also does not fully count grapheme clusters.
- **Input data:** handle null/missing and wrong types explicitly; never turn input errors into wrong business outputs.
- **Performance:** Regex and string-processing pipelines have execution costs; case-insensitive indexes do not automatically speed up every `/i` regex.
- **Security and APIs:** preserve tenant/permission filters, constrain untrusted patterns, and define expected outputs clearly.

A well-designed string-processing pipeline must use **accurate comparison rules**, **consistent Unicode units**, **edge-case safety**, and **fit real query workloads**. Understanding collation limits is the key to never conflating "locale-aware equality" with "regular expression matching" or "literal substring replacement."
